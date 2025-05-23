# bot.py
import logging
from logging.handlers import TimedRotatingFileHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from app.core.config import BOT_TOKEN, WEBAPP_URL, TON_WALLET_ADDRESS, SUBSCRIPTION_PRICE, TON_API_URL, TON_API_KEY
from app.core.database import (
    get_user_by_telegram_id,
    register_user,
    process_referral_bonus,
    add_transaction,
    get_user_by_referral_code
)
from pytonconnect import TonConnect
from pytonlib import TonlibClient
import asyncio
from dotenv import load_dotenv
from pathlib import Path
import os
import datetime
import time

load_dotenv(Path(__file__).parent.parent / '.env')

class AltaiTimeFormatter(logging.Formatter):
    def converter(self, timestamp):
        return datetime.datetime.fromtimestamp(timestamp, datetime.timezone(datetime.timedelta(hours=7)))

    def formatTime(self, record, datefmt=None):
        dt = self.converter(record.created)
        if datefmt:
            return dt.strftime(datefmt)
        else:
            return dt.isoformat()

class AltaiTimedRotatingFileHandler(TimedRotatingFileHandler):
    def shouldRollover(self, record):
        """
        Проверяет, нужно ли выполнять ротацию логов (для UTC+7)
        """
        now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))
        if now.hour == 0 and now.minute == 0 and now.second < 5:
            return True
        return False

def setup_logging():
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Log')
    os.makedirs(log_dir, exist_ok=True)
    
    log_file = os.path.join(log_dir, 'bot.log')
    
    formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    handler = logging.FileHandler(log_file, encoding='utf-8')
    handler.setFormatter(formatter)
    
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Очищаем существующие обработчики
    for h in logger.handlers[:]:
        logger.removeHandler(h)
    
    logger.addHandler(handler)

class TonPaymentProcessor:
    def __init__(self):
        self.ton = None
        self.connector = None
        
    async def init(self):
        # Минимальная конфигурация для тестов
        self.ton = TonlibClient(
            ls_index=0,
            config={
                '@type': 'config.global',
                'liteservers': [],
                'validator': {}
            },
            keystore='/tmp/ton_keystore'
        )
        await self.ton.init()
        
        self.connector = TonConnect(
            manifest_url=f'{WEBAPP_URL}/static/tonconnect-manifest.json'
        )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    referrer_code = args[0] if args else None
    user = update.effective_user
    
    # Логируем начало работы с ботом
    logging.info(f"User {user.id} started the bot with referrer: {referrer_code}")
    
    keyboard = [
        [InlineKeyboardButton(
            "💳 Купить подписку",
            web_app=WebAppInfo(url=f"{WEBAPP_URL}?user_id={user.id}")
        )]
    ]
    await update.message.reply_text(
        "Добро пожаловать!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_referral_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    referral_code = query.data.split('_')[-1]
    ref_link = f"https://t.me/{context.bot.username}?start={referral_code}"
    
    logging.info(f"Generated referral link: {ref_link}")
    
    await query.message.reply_text(
        f"Ваша реферальная ссылка:\n{ref_link}\n\n"
        "Приглашённые пользователи будут получать 30% от их покупок",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 Поделиться", url=f"tg://msg?text={ref_link}")]
        ])
    )

async def handle_ton_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = get_user_by_telegram_id(query.from_user.id)
    
    if not user.get('ton_wallet'):
        logging.warning(f"User {query.from_user.id} tried to pay without wallet")
        await query.answer("❌ Сначала привяжите TON кошелёк!")
        return
    
    try:
        await ton_processor.init()
        payment_link = await ton_processor.connector.connect(
            wallet_address=TON_WALLET_ADDRESS,
            amount=SUBSCRIPTION_PRICE*1e9,  # В нанотонах
            payload=f"sub_{user['id']}"
        )
        
        logging.info(f"Payment link generated for user {user['id']}")
        
        await query.message.reply_text(
            f"💎 Оплатите {SUBSCRIPTION_PRICE} TON",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Оплатить через TonConnect", url=payment_link)],
                [InlineKeyboardButton("✅ Проверить оплату", callback_data=f"check_payment_{user['id']}")]
            ])
        )
    except Exception as e:
        logging.error(f"Payment error for user {user['id']}: {str(e)}", exc_info=True)
        await query.message.reply_text("❌ Ошибка при создании платежа")

async def check_payment_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = int(query.data.split('_')[-1])
    
    try:
        await ton_processor.init()
        transactions = await ton_processor.ton.get_transactions(
            address=TON_WALLET_ADDRESS,
            limit=10
        )
        
        paid = any(
            tx['in_msg']['message'] == f"sub_{user_id}"
            and tx['confirmations'] >= 3
            for tx in transactions
        )
        
        if paid:
            logging.info(f"Payment confirmed for user {user_id}")
            await query.answer("✅ Оплата подтверждена!")
        else:
            logging.warning(f"Payment not found for user {user_id}")
            await query.answer("❌ Платеж не найден!", show_alert=True)
    except Exception as e:
        logging.error(f"Check payment error for user {user_id}: {str(e)}", exc_info=True)
        await query.answer("❌ Ошибка проверки платежа")

def main():
    # Инициализируем обработчик платежей
    global ton_processor
    ton_processor = TonPaymentProcessor()
    
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        
        handlers = [
            CommandHandler("start", start),
            CallbackQueryHandler(handle_referral_link, pattern="^ref_link_"),
            CallbackQueryHandler(handle_ton_payment, pattern="^buy_subscription$"),
            CallbackQueryHandler(check_payment_status, pattern="^check_payment_")
        ]
        
        application.add_handlers(handlers)
        
        logging.info("Starting bot...")
        application.run_polling()
    except Exception as e:
        logging.critical(f"Bot crashed: {str(e)}", exc_info=True)
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot stopped by user")
    except Exception as e:
        logging.critical(f"Unexpected error: {str(e)}", exc_info=True)