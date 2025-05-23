# webapp.py
from fastapi import FastAPI, Request, HTTPException
import httpx
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from app.core.database import get_user_by_telegram_id, process_referral_bonus
from pytonconnect import TonConnect
from app.core.config import TON_API_KEY, TON_WALLET_ADDRESS, SUBSCRIPTION_PRICE
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / '.env')  # Точно находит .env рядом со скриптом

app = FastAPI()
app.mount("/static", StaticFiles(directory="../static"), name="static")

@app.post("/api/init-payment")
async def init_payment(user_id: int):
    return JSONResponse({
        "wallet": TON_WALLET_ADDRESS,
        "amount": "5.0",  # 5 TON
        "payload": f"sub_{user_id}"
    })

@app.get("/api/check-payment")
async def check_payment(user_id: int):
    user_wallet = get_user_wallet(user_id)
    if not user_wallet:
        raise HTTPException(400, "Wallet not connected")
    
    async with httpx.AsyncClient() as client:
        res = await client.get(
            f"https://tonapi.io/v2/blockchain/accounts/{user_wallet}/transactions",
            headers={"Authorization": f"Bearer {TON_API_KEY}"}
        )
        
        for tx in res.json().get('transactions', []):
            if (tx['out_msgs'][0]['destination']['address'] == TON_WALLET_ADDRESS
               and tx['out_msgs'][0]['value'] >= 5000000000):  # 5 TON
                activate_subscription(user_id)
                return {"status": "paid"}
    
    return {"status": "pending"}
    
@app.get("/webapp", response_class=HTMLResponse)
async def webapp(request: Request):
    user_id = request.query_params.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID required")
    
    user = get_user_by_telegram_id(int(user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return HTMLResponse(content=f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>TON Кабинет</title>
            <script src="https://telegram.org/js/telegram-web-app.js"></script>
            <script src="/static/tonconnect.js"></script>
            <link rel="stylesheet" href="/static/style.css">
        </head>
        <body>
            <div class="container">
                <h1>Ваш баланс: {user['total_earned']} TON</h1>
                <button id="payment-button">Купить подписку</button>
            </div>
            <script>
                document.getElementById('payment-button').addEventListener('click', () => {
                    initPayment({userId: {user['id']}, amount: {SUBSCRIPTION_PRICE}});
                });
            </script>
        </body>
        </html>
    """)

@app.post("/api/verify-payment")
async def verify_payment(request: Request):
    data = await request.json()
    user_id = data.get('user_id')
    tx_hash = data.get('tx_hash')
    
    if not all([user_id, tx_hash]):
        raise HTTPException(status_code=400, detail="Invalid data")
    
    # Здесь должна быть проверка транзакции через tonlib
    process_referral_bonus(user_id, SUBSCRIPTION_PRICE)
    
    return JSONResponse({"status": "success"})

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5000)