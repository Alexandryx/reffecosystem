from mysql.connector import connect
from app.core.config import DB_CONFIG
import logging
from typing import Optional, Dict, List
import time
import secrets

logging.basicConfig(level=logging.INFO)

def get_db_connection():
    """Возвращает соединение с базой данных"""
    return connect(**DB_CONFIG)

def generate_referral_code() -> str:
    """Генерирует уникальный реферальный код"""
    return secrets.token_hex(4).upper()[:8]

# ==================== ПОЛЬЗОВАТЕЛИ ====================
def get_user_by_telegram_id(telegram_id: int) -> Optional[Dict]:
    """Получает пользователя по Telegram ID"""
    conn = get_db_connection()
    try:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute("""
                SELECT u.*, s.expires_at as subscription_end
                FROM users u
                LEFT JOIN subscriptions s ON u.id = s.user_id
                WHERE u.telegram_id = %s
                ORDER BY s.expires_at DESC LIMIT 1
            """, (telegram_id,))
            return cursor.fetchone()
    finally:
        conn.close()

def get_user_by_referral_code(referral_code: str) -> Optional[Dict]:
    """Находит пользователя по реферальному коду"""
    conn = get_db_connection()
    try:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT * FROM users WHERE referral_code = %s", (referral_code,))
            return cursor.fetchone()
    finally:
        conn.close()

def register_user(telegram_id: int, username: str, referrer_code: str = None) -> bool:
    """Регистрирует нового пользователя"""
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Проверка существующего пользователя
            cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (telegram_id,))
            if cursor.fetchone():
                return False

            # Поиск реферера
            referrer_id = None
            if referrer_code:
                cursor.execute("SELECT id FROM users WHERE referral_code = %s", (referrer_code,))
                if result := cursor.fetchone():
                    referrer_id = result[0]

            # Создание пользователя
            referral_code = generate_referral_code()
            cursor.execute("""
                INSERT INTO users 
                (telegram_id, username, referrer_id, referral_code, created_at)
                VALUES (%s, %s, %s, %s, NOW())
            """, (telegram_id, username, referrer_id, referral_code))
            
            # Начисление бонуса рефереру
            if referrer_id:
                cursor.execute("""
                    UPDATE users SET total_earned = total_earned + 5 
                    WHERE id = %s
                """, (referrer_id,))
                add_transaction(referrer_id, f"ref_signup_{telegram_id}", 5)
            
            conn.commit()
            return True
    except Exception as e:
        logging.error(f"Register error: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

# ==================== РЕФЕРАЛЬНАЯ СИСТЕМА ====================
def get_referral_info(telegram_id: int) -> Dict:
    """Возвращает статистику по рефералам (1-2 уровни)"""
    conn = get_db_connection()
    try:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute("""
                WITH RECURSIVE ref_tree AS (
                    SELECT id, 0 as level FROM users WHERE telegram_id = %s
                    UNION ALL
                    SELECT u.id, rt.level + 1
                    FROM users u JOIN ref_tree rt ON u.referrer_id = rt.id
                    WHERE rt.level < 2
                )
                SELECT 
                    level,
                    COUNT(*) as count,
                    SUM(u.total_earned) as total_earned
                FROM ref_tree rt
                JOIN users u ON rt.id = u.id
                WHERE level > 0
                GROUP BY level
            """, (telegram_id,))
            
            result = {1: {'count': 0, 'earned': 0}, 2: {'count': 0, 'earned': 0}}
            for row in cursor.fetchall():
                if row['level'] in [1, 2]:
                    result[row['level']] = {
                        'count': row['count'],
                        'earned': float(row['total_earned'] or 0)
                    }
            return result
    finally:
        conn.close()

def process_referral_bonus(user_id: int, amount: float) -> None:
    """Начисляет бонусы реферерам (30% за 1 уровень, 10% за 2 уровень)"""
    conn = get_db_connection()
    try:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute("""
                WITH RECURSIVE refs AS (
                    SELECT id, referrer_id, 1 as level FROM users WHERE id = %s
                    UNION ALL
                    SELECT u.id, u.referrer_id, r.level + 1 
                    FROM users u JOIN refs r ON u.id = r.referrer_id WHERE r.level < 2
                )
                SELECT id, level FROM refs WHERE id != %s
            """, (user_id, user_id))
            
            for ref in cursor.fetchall():
                bonus = amount * (0.3 if ref['level'] == 1 else 0.1)
                cursor.execute("""
                    UPDATE users SET total_earned = total_earned + %s 
                    WHERE id = %s
                """, (bonus, ref['id']))
                add_transaction(ref['id'], f"ref_bonus_{user_id}", bonus)
            conn.commit()
    finally:
        conn.close()

# ==================== ПЛАТЕЖИ И КОШЕЛЬКИ ====================
def get_user_wallet(telegram_id: int) -> Optional[str]:
    """Возвращает привязанный кошелек TON"""
    conn = get_db_connection()
    try:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT ton_wallet FROM users WHERE telegram_id = %s", (telegram_id,))
            result = cursor.fetchone()
            return result['ton_wallet'] if result else None
    finally:
        conn.close()

def update_wallet(telegram_id: int, wallet_address: str) -> bool:
    """Обновляет кошелек пользователя"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE users SET ton_wallet = %s 
                WHERE telegram_id = %s
            """, (wallet_address, telegram_id))
            conn.commit()
            return True
    except Exception as e:
        logging.error(f"Wallet update error: {e}")
        return False
    finally:
        conn.close()

def create_payment(telegram_id: int, amount: float) -> Optional[str]:
    """Создает запись о платеже и возвращает payment_id"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            payment_id = f"ton_{int(time.time())}"
            cursor.execute("""
                INSERT INTO payments 
                (user_id, payment_id, amount, status, created_at)
                VALUES (
                    (SELECT id FROM users WHERE telegram_id = %s),
                    %s, %s, 'pending', NOW()
                )
            """, (telegram_id, payment_id, amount))
            conn.commit()
            return payment_id
    except Exception as e:
        logging.error(f"Payment creation error: {e}")
        return None
    finally:
        conn.close()

def log_payment(telegram_id: int, tx_hash: str, amount: float) -> bool:
    """Логирует успешный платеж"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO payments 
                (user_id, tx_hash, amount, status, created_at)
                VALUES (
                    (SELECT id FROM users WHERE telegram_id = %s),
                    %s, %s, 'completed', NOW()
                )
            """, (telegram_id, tx_hash, amount))
            conn.commit()
            return True
    except Exception as e:
        logging.error(f"Payment log error: {e}")
        return False
    finally:
        conn.close()

# ==================== ПОДПИСКИ ====================
def activate_subscription(telegram_id: int, months: int = 1) -> bool:
    """Активирует/продлевает подписку"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO subscriptions (user_id, expires_at)
                VALUES (
                    (SELECT id FROM users WHERE telegram_id = %s),
                    DATE_ADD(IFNULL(
                        (SELECT MAX(expires_at) FROM subscriptions WHERE user_id = 
                         (SELECT id FROM users WHERE telegram_id = %s)),
                        NOW()
                    ), INTERVAL %s MONTH)
                )
                ON DUPLICATE KEY UPDATE expires_at = DATE_ADD(expires_at, INTERVAL %s MONTH)
            """, (telegram_id, telegram_id, months, months))
            conn.commit()
            return True
    except Exception as e:
        logging.error(f"Subscription error: {e}")
        return False
    finally:
        conn.close()

def check_subscription(telegram_id: int) -> bool:
    """Проверяет активна ли подписка"""
    conn = get_db_connection()
    try:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute("""
                SELECT expires_at > NOW() as is_active
                FROM subscriptions
                WHERE user_id = (SELECT id FROM users WHERE telegram_id = %s)
                ORDER BY expires_at DESC LIMIT 1
            """, (telegram_id,))
            result = cursor.fetchone()
            return result['is_active'] if result else False
    finally:
        conn.close()

# ==================== ТРАНЗАКЦИИ ====================
def add_transaction(user_id: int, tx_hash: str, amount: float) -> bool:
    """Добавляет запись о транзакции"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO transactions 
                (user_id, tx_hash, amount, status, created_at)
                VALUES (%s, %s, %s, 'completed', NOW())
            """, (user_id, tx_hash, amount))
            conn.commit()
            return True
    except Exception as e:
        logging.error(f"Transaction error: {e}")
        return False
    finally:
        conn.close()

def get_transactions(telegram_id: int, limit: int = 10) -> List[Dict]:
    """Возвращает историю транзакций"""
    conn = get_db_connection()
    try:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute("""
                SELECT t.* FROM transactions t
                JOIN users u ON t.user_id = u.id
                WHERE u.telegram_id = %s
                ORDER BY t.created_at DESC
                LIMIT %s
            """, (telegram_id, limit))
            return cursor.fetchall()
    finally:
        conn.close()
