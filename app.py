from main import main
import asyncio
from flask import Flask
import threading
import os

app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 RWPlugins Bot is running!"

@app.route('/health')
def health():
    return "OK"

def run_bot():
    asyncio.run(main())

if __name__ == "__main__":
    # Запускаем бота в отдельном потоке
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()
    # Запускаем Flask сервер для health check
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)