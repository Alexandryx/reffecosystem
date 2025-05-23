from mysql.connector import connect
from app.core.config import DB_CONFIG
import logging
from typing import Optional, Dict
import time

logging.basicConfig(level=logging.INFO)

def get_db_connection():
    return connect(**DB_CONFIG)

def generate_referral_code() -> str:
    import secrets
    return secrets.token_hex(4).upper()[:8]

def get_user_by_telegram_id(telegram_id: int) -> Optional[Dict]:
    conn = get_db_connection()
    try:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT * FROM users WHERE telegram_id = %s", (telegram_id,))
            return cursor.fetchone()
    finally:
        conn.close()

def get_user_by_referral_code(referral_code: str) -> Optional[Dict]:
    conn = get_db_connection()
    try:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT * FROM users WHERE referral_code = %s", (referral_code,))
            return cursor.fetchone()
    finally:
        conn.close()

def register_user(telegram_id: int, username: str, referrer_code: str = None) -> bool:
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (telegram_id,))
            if cursor.fetchone():
                return False

            referrer_id = None
            if referrer_code:
                cursor.execute("SELECT id FROM users WHERE referral_code = %s", (referrer_code,))
                if result := cursor.fetchone():
                    referrer_id = result[0]

            referral_code = generate_referral_code()
            cursor.execute("""
                INSERT INTO users 
                (telegram_id, username, referrer_id, referral_code, created_at)
                VALUES (%s, %s, %s, %s, NOW())
            """, (telegram_id, username, referrer_id, referral_code))
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

def add_transaction(user_id: int, tx_hash: str, amount: float) -> None:
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO transactions 
                (user_id, tx_hash, amount, status, created_at)
                VALUES (%s, %s, %s, 'pending', NOW())
            """, (user_id, tx_hash, amount))
            conn.commit()
    finally:
        conn.close()

def process_referral_bonus(user_id: int, amount: float) -> None:
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
                    UPDATE users SET total_earned = total_earned + %s WHERE id = %s
                """, (bonus, ref['id']))
                add_transaction(ref['id'], f"ref_{int(time.time())}", bonus)
            conn.commit()
    finally:
        conn.close()

def get_user_wallet(telegram_id: int) -> Optional[str]:
    conn = get_db_connection()
    try:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT ton_wallet FROM users WHERE telegram_id = %s", (telegram_id,))
            result = cursor.fetchone()
            return result['ton_wallet'] if result else None
    finally:
        conn.close()

def log_payment(telegram_id: int, tx_hash: str, amount: float) -> None:
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO payments (user_id, tx_hash, amount, status)
                VALUES (
                    (SELECT id FROM users WHERE telegram_id = %s),
                    %s, %s, 'pending'
                )
            """, (telegram_id, tx_hash, amount))
            conn.commit()
    finally:
        conn.close()

def activate_subscription(telegram_id: int, months: int = 1) -> None:
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO subscriptions (user_id, expires_at)
                VALUES (
                    (SELECT id FROM users WHERE telegram_id = %s),
                    DATE_ADD(NOW(), INTERVAL %s MONTH)
                )
                ON DUPLICATE KEY UPDATE expires_at = DATE_ADD(expires_at, INTERVAL %s MONTH)
            """, (telegram_id, months, months))
            conn.commit()
    finally:
        conn.close()