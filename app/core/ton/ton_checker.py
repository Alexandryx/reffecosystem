from tonlib import TonLib
from app.core.database import get_db_connection
from dotenv import load_dotenv
from pathlib import Path
from app.core.config import TON_API_KEY, TON_API_URL

load_dotenv(Path(__file__).parent / '.env')  # Точно находит .env рядом со скриптом

async def check_ton_transactions():
    ton = TonLib(TON_API_KEY)
    
    while True:
        connection = get_db_connection()
        cursor = connection.cursor()
        
        cursor.execute("""
            SELECT * FROM subscriptions 
            WHERE ton_confirmed = FALSE 
              AND ton_payment_hash IS NOT NULL
        """)
        
        for sub in cursor.fetchall():
            tx = ton.get_transaction(sub['ton_payment_hash'])
            if tx['confirmations'] >= 3:
                cursor.execute("""
                    UPDATE subscriptions
                    SET ton_confirmed = TRUE
                    WHERE id = %s
                """, (sub['id'],))
        
        connection.commit()
        cursor.close()
        connection.close()
        
        await asyncio.sleep(30)  # Проверка каждые 30 секунд