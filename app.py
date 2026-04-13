import asyncio
import threading
import logging
import os
from flask import Flask

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 RWPlugins Bot is running!"

@app.route('/health')
def health():
    return "OK"

def run_bot():
    """Запуск бота в отдельном потоке"""
    try:
        logger.info("🟢 Запускаем бота в потоке...")
        from main import main
        asyncio.run(main())
    except Exception as e:
        logger.error(f"🔴 Бот упал с ошибкой: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    logger.info("🟡 Запуск приложения...")
    
    # Запускаем бота в фоновом потоке
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    logger.info("🟢 Поток бота запущен")
    
    # Запускаем Flask сервер
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🟡 Запускаем Flask на порту {port}")
    app.run(host='0.0.0.0', port=port)
