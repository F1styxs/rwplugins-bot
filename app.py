import asyncio
from flask import Flask
import os

app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 RWPlugins Bot is running!"

@app.route('/health')
def health():
    return "OK"

if __name__ == "__main__":
    # Запускаем бота в том же потоке
    async def start_bot():
        from main import main
        await main()
    
    # Запускаем Flask в отдельном потоке
    import threading
    def run_flask():
        port = int(os.environ.get("PORT", 8080))
        app.run(host='0.0.0.0', port=port)
    
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Запускаем бота
    asyncio.run(start_bot())
