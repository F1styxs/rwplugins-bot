from main import main
import asyncio
from flask import Flask
import os
import threading

app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 RWPlugins Bot is running!"

@app.route('/health')
def health():
    return "OK"

def run_bot():
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Бот упал с ошибкой: {e}")

if __name__ == "__main__":
    # Запускаем бота в потоке
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Запускаем Flask сервер
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
