# init_db.py
from app.core.database import get_db_connection
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / '.env')  # Точно находит .env рядом со скриптом

def init_database():
    connection = get_db_connection()
    cursor = connection.cursor()

    # Таблица пользователей
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        telegram_id BIGINT UNIQUE NOT NULL,
        username VARCHAR(255),
        ton_wallet VARCHAR(64) UNIQUE,
        created_at DATETIME NOT NULL,
        referrer_id INT,
        referral_code VARCHAR(8) UNIQUE,
        total_earned DECIMAL(18,9) DEFAULT 0.0,
        subscription_expires DATETIME,
        FOREIGN KEY (referrer_id) REFERENCES users(id)
    )
    """)

    # Таблица транзакций
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        tx_hash VARCHAR(64) UNIQUE,
        amount DECIMAL(18,9),
        status ENUM('pending','confirmed','failed'),
        created_at DATETIME NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """)

    # Таблица реферальных связей
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS referrals (
        id INT AUTO_INCREMENT PRIMARY KEY,
        referrer_id INT NOT NULL,
        referral_id INT NOT NULL UNIQUE,
        level INT NOT NULL,
        created_at DATETIME NOT NULL,
        FOREIGN KEY (referrer_id) REFERENCES users(id),
        FOREIGN KEY (referral_id) REFERENCES users(id)
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        tx_hash VARCHAR(64) UNIQUE,
        amount DECIMAL(18,9),
        status ENUM('pending','confirmed','failed'),
        created_at DATETIME DEFAULT NOW(),
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
""")

    connection.commit()
    cursor.close()
    connection.close()

if __name__ == "__main__":
    init_database()