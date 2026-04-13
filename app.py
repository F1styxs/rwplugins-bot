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

# Создаём отдельный event loop для бота
def run_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        from main import main
        loop.run_until_complete(main())
    except Exception as e:
        print(f"Ошибка бота: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Запускаем бота в фоновом потоке
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Запускаем Flask
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
