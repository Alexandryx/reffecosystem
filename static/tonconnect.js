// tonconnect.js
let connector = null;

async function initPayment(params) {
    if (!connector) {
        connector = new TonConnect.TonConnect({
            manifestUrl: 'https://ваш-домен/tonconnect-manifest.json'
        });
    }

    try {
        const tx = {
            validUntil: Math.floor(Date.now() / 1000) + 3600,
            messages: [{
                address: params.wallet || 'ВАШ_TON_КОШЕЛЁК',
                amount: String(params.amount * 1e9),
                payload: `sub_${params.userId}`
            }]
        };

        const result = await connector.sendTransaction(tx);
        
        fetch('/api/verify-payment', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                user_id: params.userId,
                tx_hash: result.boc
            })
        });
    } catch (error) {
        console.error('Payment error:', error);
        Telegram.WebApp.showAlert('Ошибка платежа: ' + error.message);
    }
}