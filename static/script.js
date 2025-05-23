// Данные для каждого овала
const matrixData = {
    1: { title: "Основной VIP", id: "matrix-vip" },
    2: { title: "Теннис VIP", id: "matrix-tennis" },
    3: { title: "Бои VIP", id: "matrix-fights" },
    4: { title: "Kriptano VIP", id: "matrix-kriptano" },
    5: { title: "Lukas VIP", id: "matrix-lukas" },
    6: { title: "ХЗ пока VIP", id: "matrix-unknown" },
    7: { title: "ВИДЕО 1", id: "matrix-video1" },
    8: { title: "ВИДЕО 2", id: "matrix-video2" },
    9: { title: "ВИДЕО 3", id: "matrix-video3" },
};

// Обработка кликов по овалам
document.querySelectorAll('.oval').forEach(oval => {
    oval.addEventListener('click', handleOvalClick);
    oval.addEventListener('touchstart', handleOvalClick);
});

function handleOvalClick(event) {
    event.preventDefault();

    // Сбрасываем все овалы
    document.querySelectorAll('.oval').forEach(o => {
        o.classList.remove('active');
    });

    // Активируем выбранный овал
    const oval = event.currentTarget;
    oval.classList.add('active');

    // Получаем данные для выбранного овала
    const level = oval.getAttribute('data-level');
    const { title, id } = matrixData[level];

    // Обновляем заголовок матрицы
    document.getElementById('matrix-title').textContent = title;

    // Скрываем все блоки матриц
    document.querySelectorAll('.matrix-container').forEach(container => {
        container.style.display = 'none';
    });

    // Показываем нужный блок матрицы
    document.getElementById(id).style.display = 'block';
}

    // Подключение TonConnect
    const connector = new TonConnect.TonConnect({
    manifestUrl: window.location.origin + '/static/tonconnect-manifest.json'
});

    // Инициализация платежа
    async function initPayment(userId) {
    const response = await fetch(`/api/init-payment?user_id=${userId}`);
    const { wallet, amount, payload } = await response.json();
    
    const tx = {
        validUntil: Math.floor(Date.now() / 1000) + 300,  // 5 мин
        messages: [{
            address: wallet,
            amount: String(Number(amount) * 1e9),  // Конвертируем в нанотоны
            payload
        }]
    };
    
    try {
        const result = await connector.sendTransaction(tx);
        await verifyPayment(userId, result.boc);
    } catch (error) {
        Telegram.WebApp.showAlert(`Ошибка: ${error.message}`);
    }
}

    // Проверка платежа
    async function verifyPayment(userId, txHash) {
    const response = await fetch(`/api/check-payment?user_id=${userId}&tx_hash=${txHash}`);
    const { status } = await response.json();
    
    if (status === 'paid') {
        Telegram.WebApp.showAlert('Оплата подтверждена!');
        Telegram.WebApp.close();
    } else {
        setTimeout(() => verifyPayment(userId, txHash), 5000);  // Повторная проверка
    }
}