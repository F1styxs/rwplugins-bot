import asyncio
import os
import sqlite3
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# Настройки
logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# ВЛАДЕЛЬЦЫ - добавляй ID через запятую
OWNERS = [7130414548]

# Дата создания магазина
SHOP_CREATION_DATE = "15.04.2025"

if not BOT_TOKEN:
    print("❌ Токен не найден!")
    exit(1)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ---------- СОСТОЯНИЯ ----------
class UploadPlugin(StatesGroup):
    waiting_for_file = State()
    waiting_for_name = State()
    waiting_for_price = State()
    waiting_for_category = State()
    waiting_for_description = State()

class TicketStates(StatesGroup):
    waiting_for_question = State()
    admin_waiting_for_reply = State()
    admin_waiting_for_ticket_selection = State()

class RatingStates(StatesGroup):
    waiting_for_rating = State()

# ---------- БД ----------
def init_db():
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE)')
    cur.execute('CREATE TABLE IF NOT EXISTS plugins (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, category_id INTEGER, description TEXT, price INTEGER DEFAULT 0, file_path TEXT, downloads_count INTEGER DEFAULT 0, rating_sum INTEGER DEFAULT 0, rating_count INTEGER DEFAULT 0)')
    cur.execute('CREATE TABLE IF NOT EXISTS tickets (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, question TEXT, answer TEXT, status TEXT DEFAULT "open", created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    cur.execute('CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, added_by INTEGER, added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    cur.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, total_downloads INTEGER DEFAULT 0)')
    cur.execute('CREATE TABLE IF NOT EXISTS ratings (id INTEGER PRIMARY KEY AUTOINCREMENT, plugin_id INTEGER, user_id INTEGER, rating INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    conn.commit()
    conn.close()
    print("✅ База данных готова")

def register_user(user_id):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def add_category(name):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (name,))
    conn.commit()
    conn.close()

def get_categories():
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM categories")
    data = cur.fetchall()
    conn.close()
    return data

def delete_category(category_id):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    conn.commit()
    conn.close()

def add_plugin(name, category_id, price, description, file_path):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute('INSERT INTO plugins (name, category_id, price, description, file_path, downloads_count, rating_sum, rating_count) VALUES (?, ?, ?, ?, ?, 0, 0, 0)', (name, category_id, price, description, file_path))
    conn.commit()
    conn.close()

def get_plugins_by_category(category_id):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute('SELECT id, name, description, price, file_path, downloads_count, rating_sum, rating_count FROM plugins WHERE category_id = ?', (category_id,))
    data = cur.fetchall()
    conn.close()
    return data

def get_all_plugins():
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute('SELECT id, name, category_id, price, description, downloads_count, rating_sum, rating_count FROM plugins')
    data = cur.fetchall()
    conn.close()
    return data

def increment_downloads(plugin_id, user_id):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("UPDATE plugins SET downloads_count = downloads_count + 1 WHERE id = ?", (plugin_id,))
    conn.commit()
    conn.close()

def add_rating(plugin_id, user_id, rating):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT id FROM ratings WHERE plugin_id = ? AND user_id = ?", (plugin_id, user_id))
    if cur.fetchone():
        conn.close()
        return False
    cur.execute("INSERT INTO ratings (plugin_id, user_id, rating) VALUES (?, ?, ?)", (plugin_id, user_id, rating))
    cur.execute("UPDATE plugins SET rating_sum = rating_sum + ?, rating_count = rating_count + 1 WHERE id = ?", (rating, plugin_id))
    conn.commit()
    conn.close()
    return True

def get_plugin_rating(plugin_id):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT rating_sum, rating_count FROM plugins WHERE id = ?", (plugin_id,))
    rating_sum, rating_count = cur.fetchone()
    conn.close()
    if rating_count == 0:
        return 0, 0
    return round(rating_sum / rating_count, 1), rating_count

def create_ticket(user_id, question):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("INSERT INTO tickets (user_id, question, status) VALUES (?, ?, 'open')", (user_id, question))
    conn.commit()
    ticket_id = cur.lastrowid
    conn.close()
    return ticket_id

def get_user_ticket(user_id):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT id, question, answer, status, created_at FROM tickets WHERE user_id = ? AND status = 'open' ORDER BY id DESC LIMIT 1", (user_id,))
    data = cur.fetchone()
    conn.close()
    return data

def get_all_open_tickets():
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT id, user_id, question, created_at FROM tickets WHERE status = 'open' ORDER BY created_at DESC")
    data = cur.fetchall()
    conn.close()
    return data

def get_ticket_by_id(ticket_id):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT id, user_id, question, answer, status FROM tickets WHERE id = ?", (ticket_id,))
    data = cur.fetchone()
    conn.close()
    return data

def answer_ticket(ticket_id, answer):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("UPDATE tickets SET answer = ?, status = 'closed' WHERE id = ?", (answer, ticket_id))
    conn.commit()
    conn.close()

def is_admin(user_id):
    if user_id in OWNERS:
        return True
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
    res = cur.fetchone()
    conn.close()
    return res is not None

def add_admin(admin_id, added_by):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO admins (user_id, added_by) VALUES (?, ?)", (admin_id, added_by))
    conn.commit()
    conn.close()

def remove_admin(admin_id):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("DELETE FROM admins WHERE user_id = ?", (admin_id,))
    conn.commit()
    conn.close()

def get_admins():
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT user_id, added_by, added_at FROM admins")
    data = cur.fetchall()
    conn.close()
    return data

def get_total_users():
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    total = cur.fetchone()[0]
    conn.close()
    return total

# ---------- КЛАВИАТУРЫ (Reply Keyboard - внизу экрана) ----------
def get_main_keyboard():
    """Клавиатура для обычного пользователя"""
    kb = [
        [KeyboardButton(text="📂 Категории"), KeyboardButton(text="📋 Список товаров")],
        [KeyboardButton(text="ℹ️ О магазине"), KeyboardButton(text="👤 Мой профиль")],
        [KeyboardButton(text="📜 Правила"), KeyboardButton(text="🆘 Поддержка")],
        [KeyboardButton(text="⭐ Оценить плагин")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_admin_keyboard():
    """Клавиатура для админа/владельца"""
    kb = [
        [KeyboardButton(text="📂 Категории"), KeyboardButton(text="📋 Список товаров")],
        [KeyboardButton(text="ℹ️ О магазине"), KeyboardButton(text="👤 Мой профиль")],
        [KeyboardButton(text="📜 Правила"), KeyboardButton(text="🆘 Поддержка")],
        [KeyboardButton(text="⭐ Оценить плагин"), KeyboardButton(text="⚙️ Админ-панель")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_admin_panel_keyboard():
    """Клавиатура админ-панели"""
    kb = [
        [KeyboardButton(text="📥 Загрузить плагин")],
        [KeyboardButton(text="➕ Добавить категорию"), KeyboardButton(text="🗑 Удалить категорию")],
        [KeyboardButton(text="👥 Управление админами"), KeyboardButton(text="👑 Управление владельцами")],
        [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="🎫 Тикеты")],
        [KeyboardButton(text="📈 Рейтинг плагинов"), KeyboardButton(text="◀ Назад в меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def back_keyboard():
    """Клавиатура с кнопкой назад"""
    kb = [[KeyboardButton(text="◀ Назад в меню")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def rating_keyboard(plugin_name):
    kb = [
        [KeyboardButton(text="⭐ 1"), KeyboardButton(text="⭐ 2"), KeyboardButton(text="⭐ 3")],
        [KeyboardButton(text="⭐ 4"), KeyboardButton(text="⭐ 5"), KeyboardButton(text="◀ Назад в меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# ---------- ОБРАБОТЧИКИ ----------
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    register_user(user_id)
    
    if is_admin(user_id):
        await message.answer(
            "🏪 **RWPlugins - Ключ к созданию большего!**\n\n"
            f"👑 Ваша роль: {'Владелец' if user_id in OWNERS else 'Администратор'}\n\n"
            "Добро пожаловать в админ-панель!",
            reply_markup=get_admin_keyboard()
        )
    else:
        await message.answer(
            "🏪 **RWPlugins - Ключ к созданию большего!**\n\n"
            "Добро пожаловать в магазин плагинов!\n\n"
            "📌 Используйте кнопки ниже для навигации:",
            reply_markup=get_main_keyboard()
        )

@dp.message(F.text == "◀ Назад в меню")
async def back_to_menu(message: types.Message):
    user_id = message.from_user.id
    if is_admin(user_id):
        await message.answer("⚙️ **Главное меню**", reply_markup=get_admin_keyboard())
    else:
        await message.answer("🏪 **Главное меню**", reply_markup=get_main_keyboard())

@dp.message(F.text == "⚙️ Админ-панель")
async def open_admin_panel(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет доступа к админ-панели!", reply_markup=get_main_keyboard())
        return
    await message.answer("⚙️ **Панель администратора**\n\nВыберите действие:", reply_markup=get_admin_panel_keyboard())

# ---------- КАТЕГОРИИ ----------
@dp.message(F.text == "📂 Категории")
async def show_categories(message: types.Message):
    cats = get_categories()
    if not cats:
        await message.answer("❌ Категорий пока нет.", reply_markup=back_keyboard())
        return
    
    text = "📂 **Категории товаров:**\n\n"
    kb = []
    for cat_id, cat_name in cats:
        text += f"• {cat_name}\n"
        kb.append([KeyboardButton(text=f"📁 {cat_name}")])
    kb.append([KeyboardButton(text="◀ Назад в меню")])
    
    await message.answer(text, reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))

@dp.message(F.text.startswith("📁 "))
async def show_plugins_in_category(message: types.Message):
    cat_name = message.text.replace("📁 ", "")
    
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT id FROM categories WHERE name = ?", (cat_name,))
    cat = cur.fetchone()
    if not cat:
        await message.answer("❌ Категория не найдена")
        return
    cat_id = cat[0]
    
    plugins = get_plugins_by_category(cat_id)
    conn.close()
    
    if not plugins:
        await message.answer("❌ В этой категории пока нет плагинов.", reply_markup=back_keyboard())
        return
    
    text = f"📁 **{cat_name}**\n\n"
    kb = []
    for pid, name, desc, price, fpath, downloads, rating_sum, rating_count in plugins:
        rating, count = get_plugin_rating(pid)
        stars = "⭐" * int(rating) if rating > 0 else "Нет оценок"
        text += f"🔹 **{name}**\n   💰 {price} ₽\n   ⬇️ {downloads}\n   🌟 {rating} {stars}\n\n"
        kb.append([KeyboardButton(text=f"📥 Купить {name}")])
    
    kb.append([KeyboardButton(text="◀ Назад в меню")])
    await message.answer(text, reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))

# ---------- СПИСОК ТОВАРОВ ----------
@dp.message(F.text == "📋 Список товаров")
async def all_products(message: types.Message):
    plugins = get_all_plugins()
    if not plugins:
        await message.answer("📭 Товаров пока нет.", reply_markup=back_keyboard())
        return
    
    text = "📦 **Все товары RWPlugins:**\n\n"
    kb = []
    for pid, name, cat_id, price, desc, downloads, rating_sum, rating_count in plugins:
        rating, count = get_plugin_rating(pid)
        stars = "⭐" * int(rating) if rating > 0 else "Нет оценок"
        text += f"🔹 **{name}**\n   💰 {price} ₽\n   ⬇️ {downloads}\n   🌟 {rating} {stars}\n   📝 {desc}\n\n"
        kb.append([KeyboardButton(text=f"📥 Купить {name}")])
    
    kb.append([KeyboardButton(text="◀ Назад в меню")])
    await message.answer(text, reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))

# ---------- ПОКУПКА ----------
@dp.message(F.text.startswith("📥 Купить "))
async def buy_plugin(message: types.Message):
    plugin_name = message.text.replace("📥 Купить ", "")
    
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT id, file_path, price, name FROM plugins WHERE name = ?", (plugin_name,))
    res = cur.fetchone()
    conn.close()
    
    if not res:
        await message.answer("❌ Плагин не найден")
        return
    
    plugin_id, file_path, price, name = res
    
    if os.path.exists(file_path):
        increment_downloads(plugin_id, message.from_user.id)
        doc = FSInputFile(file_path)
        await message.answer_document(doc, caption=f"✅ **{name}** успешно скачан!\n💰 Цена: {price} ₽")
        
        # Предлагаем оценить
        kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=f"⭐ Оценить {name}")], [KeyboardButton(text="◀ Назад в меню")]], resize_keyboard=True)
        await message.answer("⭐ Понравился плагин? Оцени его!", reply_markup=kb)
    else:
        await message.answer("❌ Файл временно недоступен. Обратитесь в поддержку.")

# ---------- ОЦЕНКА ПЛАГИНОВ ----------
@dp.message(F.text.startswith("⭐ Оценить "))
async def start_rating(message: types.Message, state: FSMContext):
    plugin_name = message.text.replace("⭐ Оценить ", "")
    
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT id FROM plugins WHERE name = ?", (plugin_name,))
    res = cur.fetchone()
    conn.close()
    
    if not res:
        await message.answer("❌ Плагин не найден")
        return
    
    plugin_id = res[0]
    await state.update_data(plugin_id=plugin_id, plugin_name=plugin_name)
    await message.answer(f"⭐ Оцените плагин **{plugin_name}** от 1 до 5:", reply_markup=rating_keyboard(plugin_name))
    await state.set_state(RatingStates.waiting_for_rating)

@dp.message(RatingStates.waiting_for_rating, F.text.startswith("⭐ "))
async def process_rating(message: types.Message, state: FSMContext):
    try:
        rating = int(message.text.replace("⭐ ", ""))
        if rating < 1 or rating > 5:
            await message.answer("❌ Оценка должна быть от 1 до 5!")
            return
    except:
        await message.answer("❌ Пожалуйста, выберите оценку из кнопок!")
        return
    
    data = await state.get_data()
    plugin_id = data.get("plugin_id")
    plugin_name = data.get("plugin_name")
    user_id = message.from_user.id
    
    if add_rating(plugin_id, user_id, rating):
        rating_val, count = get_plugin_rating(plugin_id)
        user_role = is_admin(user_id)
        await message.answer(f"✅ Спасибо за оценку! 🌟 Средний рейтинг: {rating_val} ⭐ ({count} оценок)", 
                           reply_markup=get_admin_keyboard() if user_role else get_main_keyboard())
    else:
        user_role = is_admin(user_id)
        await message.answer("❌ Вы уже оценивали этот плагин!", 
                           reply_markup=get_admin_keyboard() if user_role else get_main_keyboard())
    
    await state.clear()

@dp.message(F.text == "⭐ Оценить плагин")
async def rate_plugin_menu(message: types.Message):
    plugins = get_all_plugins()
    if not plugins:
        await message.answer("📭 Нет плагинов для оценки.", reply_markup=back_keyboard())
        return
    
    kb = []
    for pid, name, cat_id, price, desc, downloads, rating_sum, rating_count in plugins:
        kb.append([KeyboardButton(text=f"⭐ Оценить {name}")])
    kb.append([KeyboardButton(text="◀ Назад в меню")])
    
    await message.answer("⭐ Выберите плагин для оценки:", reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))

# ---------- ИНФОРМАЦИОННЫЕ КНОПКИ ----------
@dp.message(F.text == "ℹ️ О магазине")
async def about_shop(message: types.Message):
    text = "🏪 **RWPlugins - Ключ к созданию большего!**\n\n"
    text += "Мы создаём качественные плагины для Minecraft.\n"
    text += f"📅 Магазин работает с {SHOP_CREATION_DATE}\n\n"
    text += "В нашем ассортименте:\n"
    text += "• PvP системы\n• Экономика\n• Босс-арены\n• Кейсы и лутбоксы\n\n"
    text += "💬 По вопросам: @owner_rwplugins"
    await message.answer(text, reply_markup=back_keyboard())

@dp.message(F.text == "👤 Мой профиль")
async def profile(message: types.Message):
    user_id = message.from_user.id
    user_role = "Владелец" if user_id in OWNERS else "Администратор" if is_admin(user_id) else "Покупатель"
    
    text = f"👤 **Мой профиль RWPlugins**\n\n"
    text += f"🆔 ID: {user_id}\n"
    text += f"📅 Дата регистрации: {datetime.now().strftime('%d.%m.%Y')}\n"
    text += f"👑 Роль: {user_role}"
    await message.answer(text, reply_markup=back_keyboard())

@dp.message(F.text == "📜 Правила")
async def rules(message: types.Message):
    text = "📜 **Правила магазина RWPlugins**\n\n"
    text += "1. Запрещён возврат средств после скачивания\n"
    text += "2. Все плагины проверены\n"
    text += "3. Техподдержка отвечает в течение 24 часов\n"
    text += "4. Запрещено распространять плагины\n\n"
    text += f"📅 Магазин работает с {SHOP_CREATION_DATE}"
    await message.answer(text, reply_markup=back_keyboard())

# ---------- ПОДДЕРЖКА (ТИКЕТЫ) ----------
@dp.message(F.text == "🆘 Поддержка")
async def support_start(message: types.Message, state: FSMContext):
    existing_ticket = get_user_ticket(message.from_user.id)
    if existing_ticket:
        ticket_id, question, answer, status, created_at = existing_ticket
        await message.answer(f"❌ У вас уже есть активный тикет #{ticket_id}!\nОжидайте ответа администратора.")
        return
    
    await message.answer("📝 Напишите ваш вопрос подробно. Администратор ответит вам в этом чате:")
    await state.set_state(TicketStates.waiting_for_question)

@dp.message(TicketStates.waiting_for_question, F.text)
async def create_ticket_handler(message: types.Message, state: FSMContext):
    ticket_id = create_ticket(message.from_user.id, message.text)
    await message.answer(f"✅ **Тикет #{ticket_id} создан!**\n\nАдминистратор ответит вам здесь. Ожидайте.")
    await state.clear()
    
    # Уведомляем админов и владельцев
    for admin_id in OWNERS:
        try:
            await bot.send_message(admin_id, f"🆕 **Новый тикет #{ticket_id}**\n👤 От: {message.from_user.id}\n📝 Вопрос: {message.text[:100]}...")
        except:
            pass
    for admin_id, _, _ in get_admins():
        try:
            await bot.send_message(admin_id, f"🆕 **Новый тикет #{ticket_id}**\n👤 От: {message.from_user.id}\n📝 Вопрос: {message.text[:100]}...")
        except:
            pass

# ---------- АДМИН: ТИКЕТЫ ----------
@dp.message(F.text == "🎫 Тикеты")
async def admin_view_tickets(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа")
        return
    
    tickets = get_all_open_tickets()
    if not tickets:
        await message.answer("📭 Нет активных тикетов.", reply_markup=get_admin_panel_keyboard())
        return
    
    text = "🎫 **Активные тикеты:**\n\n"
    kb = []
    for ticket_id, user_id, question, created_at in tickets:
        text += f"#{ticket_id} | От: {user_id}\n📝 {question[:50]}...\n🕐 {created_at}\n\n"
        kb.append([KeyboardButton(text=f"📝 Ответить на тикет #{ticket_id}")])
    
    kb.append([KeyboardButton(text="◀ Назад в меню")])
    await message.answer(text, reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))
    await state.set_state(TicketStates.admin_waiting_for_ticket_selection)

@dp.message(TicketStates.admin_waiting_for_ticket_selection, F.text.startswith("📝 Ответить на тикет #"))
async def admin_reply_to_ticket(message: types.Message, state: FSMContext):
    ticket_id = int(message.text.split("#")[1])
    ticket = get_ticket_by_id(ticket_id)
    
    if not ticket:
        await message.answer("❌ Тикет не найден")
        await state.clear()
        return
    
    await state.update_data(ticket_id=ticket_id, user_id=ticket[1])
    await message.answer(f"📝 Введите ответ для пользователя (тикет #{ticket_id}):\n\n📩 Вопрос: {ticket[2]}")
    await state.set_state(TicketStates.admin_waiting_for_reply)

@dp.message(TicketStates.admin_waiting_for_reply, F.text)
async def admin_send_reply(message: types.Message, state: FSMContext):
    data = await state.get_data()
    ticket_id = data.get("ticket_id")
    user_id = data.get("user_id")
    answer = message.text
    
    answer_ticket(ticket_id, answer)
    
    try:
        await bot.send_message(
            user_id,
            f"📨 **Ответ поддержки** (тикет #{ticket_id})\n\n{answer}\n\n✅ Тикет закрыт. Спасибо за обращение!"
        )
        await message.answer(f"✅ Ответ отправлен пользователю {user_id}. Тикет #{ticket_id} закрыт.")
    except Exception as e:
        await message.answer(f"❌ Не удалось отправить: {e}")
    
    await state.clear()
    await message.answer("⚙️ Админ-панель", reply_markup=get_admin_panel_keyboard())

# ---------- АДМИН: ЗАГРУЗКА ПЛАГИНА ----------
@dp.message(F.text == "📥 Загрузить плагин")
async def admin_upload_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа")
        return
    await message.answer("📎 Отправьте файл плагина (zip, py, jar):")
    await state.set_state(UploadPlugin.waiting_for_file)

@dp.message(StateFilter(UploadPlugin.waiting_for_file), F.document)
async def get_plugin_file(message: types.Message, state: FSMContext):
    doc = message.document
    file_path = f"plugins/{doc.file_name}"
    os.makedirs("plugins", exist_ok=True)
    file = await bot.get_file(doc.file_id)
    await bot.download_file(file.file_path, file_path)
    await state.update_data(file_path=file_path)
    await message.answer("✏️ Введите **название** плагина:")
    await state.set_state(UploadPlugin.waiting_for_name)

@dp.message(StateFilter(UploadPlugin.waiting_for_name), F.text)
async def get_plugin_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("💰 Введите **цену** в рублях (например: 350):")
    await state.set_state(UploadPlugin.waiting_for_price)

@dp.message(StateFilter(UploadPlugin.waiting_for_price), F.text)
async def get_plugin_price(message: types.Message, state: FSMContext):
    try:
        price = int(message.text)
        await state.update_data(price=price)
        cats = get_categories()
        if not cats:
            await message.answer("⚠️ Сначала создайте категорию в админ-панели!")
            await state.clear()
            return
        kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=cat_name)] for _, cat_name in cats], resize_keyboard=True)
        await message.answer("📂 Выберите категорию:", reply_markup=kb)
        await state.set_state(UploadPlugin.waiting_for_category)
    except:
        await message.answer("❌ Введите число!")

@dp.message(StateFilter(UploadPlugin.waiting_for_category), F.text)
async def get_plugin_category(message: types.Message, state: FSMContext):
    cat_name = message.text
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT id FROM categories WHERE name = ?", (cat_name,))
    cat = cur.fetchone()
    conn.close()
    
    if not cat:
        await message.answer("❌ Категория не найдена! Используйте кнопки.")
        return
    
    await state.update_data(category_id=cat[0])
    await message.answer("📝 Введите **описание** плагина:")
    await state.set_state(UploadPlugin.waiting_for_description)

@dp.message(StateFilter(UploadPlugin.waiting_for_description), F.text)
async def finish_upload(message: types.Message, state: FSMContext):
    data = await state.get_data()
    add_plugin(data['name'], data['category_id'], data['price'], message.text, data['file_path'])
    await message.answer(f"✅ **Плагин {data['name']} добавлен!**", reply_markup=get_admin_panel_keyboard())
    await state.clear()

# ---------- АДМИН: КАТЕГОРИИ ----------
@dp.message(F.text == "➕ Добавить категорию")
async def admin_add_category_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа")
        return
    await message.answer("📝 Введите название новой категории:")
    await state.set_state("waiting_for_category")

@dp.message(StateFilter("waiting_for_category"), F.text)
async def admin_add_category(message: types.Message, state: FSMContext):
    add_category(message.text)
    await message.answer(f"✅ Категория **{message.text}** добавлена!", reply_markup=get_admin_panel_keyboard())
    await state.clear()

@dp.message(F.text == "🗑 Удалить категорию")
async def admin_del_category_menu(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа")
        return
    cats = get_categories()
    if not cats:
        await message.answer("❌ Нет категорий для удаления.")
        return
    kb = [[KeyboardButton(text=f"🗑 {cat_name}")] for _, cat_name in cats]
    kb.append([KeyboardButton(text="◀ Назад в меню")])
    await message.answer("🗑 Выберите категорию для удаления:", reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))

@dp.message(F.text.startswith("🗑 ") and F.text != "🗑 Удалить категорию" and not F.text.startswith("🗑 Удалить админа"))
async def confirm_delete_category(message: types.Message):
    cat_name = message.text.replace("🗑 ", "")
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT id FROM categories WHERE name = ?", (cat_name,))
    cat_id = cur.fetchone()
    conn.close()
    if cat_id:
        delete_category(cat_id[0])
        await message.answer(f"✅ Категория '{cat_name}' удалена!")
    else:
        await message.answer("❌ Категория не найдена")
    await message.answer("⚙️ Админ-панель", reply_markup=get_admin_panel_keyboard())

# ---------- АДМИН: УПРАВЛЕНИЕ АДМИНАМИ ----------
@dp.message(F.text == "👥 Управление админами")
async def admin_manage_admins(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа")
        return
    
    kb = [
        [KeyboardButton(text="➕ Добавить админа")],
        [KeyboardButton(text="🗑 Удалить админа")],
        [KeyboardButton(text="📋 Список админов")],
        [KeyboardButton(text="◀ Назад в меню")]
    ]
    await message.answer("👥 **Управление администраторами**", reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))

@dp.message(F.text == "➕ Добавить админа")
async def add_admin_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in OWNERS:
        await message.answer("⛔ Только владельцы могут добавлять админов!")
        return
    await message.answer("📝 Введите Telegram ID пользователя:")
    await state.set_state("waiting_for_admin_id")

@dp.message(StateFilter("waiting_for_admin_id"), F.text)
async def add_admin_process(message: types.Message, state: FSMContext):
    try:
        admin_id = int(message.text)
        if admin_id in OWNERS:
            await message.answer("❌ Этот пользователь уже владелец!")
        else:
            add_admin(admin_id, message.from_user.id)
            await message.answer(f"✅ Пользователь `{admin_id}` теперь администратор!")
    except:
        await message.answer("❌ Неверный ID! Введите число.")
    await state.clear()
    await message.answer("⚙️ Админ-панель", reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "🗑 Удалить админа")
async def remove_admin_menu(message: types.Message):
    if message.from_user.id not in OWNERS:
        await message.answer("⛔ Только владельцы могут удалять админов!")
        return
    admins = get_admins()
    if not admins:
        await message.answer("❌ Нет администраторов для удаления.")
        return
    kb = [[KeyboardButton(text=f"🗑 Удалить админа {admin_id}")] for admin_id, _, _ in admins]
    kb.append([KeyboardButton(text="◀ Назад в меню")])
    await message.answer("🗑 Выберите администратора для удаления:", reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))

@dp.message(F.text.startswith("🗑 Удалить админа "))
async def remove_admin_process(message: types.Message):
    try:
        admin_id = int(message.text.replace("🗑 Удалить админа ", ""))
        if admin_id in OWNERS:
            await message.answer("❌ Нельзя удалить владельца через удаление админа!")
            return
        remove_admin(admin_id)
        await message.answer(f"✅ Администратор {admin_id} удалён!")
    except:
        await message.answer("❌ Ошибка!")
    await message.answer("⚙️ Админ-панель", reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "📋 Список админов")
async def list_admins(message: types.Message):
    admins = get_admins()
    text = "👑 **Владельцы:**\n"
    for owner_id in OWNERS:
        text += f"• `{owner_id}`\n"
    text += "\n👥 **Администраторы:**\n"
    if admins:
        for admin_id, added_by, added_at in admins:
            text += f"• `{admin_id}` (добавлен {added_at[:10]})\n"
    else:
        text += "Нет администраторов\n"
    await message.answer(text, reply_markup=get_admin_panel_keyboard())

# ---------- АДМИН: УПРАВЛЕНИЕ ВЛАДЕЛЬЦАМИ ----------
@dp.message(F.text == "👑 Управление владельцами")
async def owner_manage(message: types.Message):
    if message.from_user.id not in OWNERS:
        await message.answer("⛔ Только владельцы могут управлять владельцами!")
        return
    
    kb = [
        [KeyboardButton(text="➕ Добавить владельца")],
        [KeyboardButton(text="📋 Список владельцев")],
        [KeyboardButton(text="◀ Назад в меню")]
    ]
    await message.answer("👑 **Управление владельцами**", reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))

@dp.message(F.text == "➕ Добавить владельца")
async def add_owner_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in OWNERS:
        await message.answer("⛔ Нет прав!")
        return
    await message.answer("📝 Введите Telegram ID нового владельца:")
    await state.set_state("waiting_for_owner_id")

@dp.message(StateFilter("waiting_for_owner_id"), F.text)
async def add_owner_process(message: types.Message, state: FSMContext):
    try:
        owner_id = int(message.text)
        if owner_id not in OWNERS:
            OWNERS.append(owner_id)
            await message.answer(f"✅ Пользователь `{owner_id}` теперь владелец!")
        else:
            await message.answer("❌ Пользователь уже владелец!")
    except:
        await message.answer("❌ Неверный ID!")
    await state.clear()
    await message.answer("⚙️ Админ-панель", reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "📋 Список владельцев")
async def list_owners(message: types.Message):
    text = "👑 **Список владельцев:**\n\n"
    for owner_id in OWNERS:
        text += f"• `{owner_id}`\n"
    await message.answer(text, reply_markup=get_admin_panel_keyboard())

# ---------- АДМИН: СТАТИСТИКА И РЕЙТИНГ ----------
@dp.message(F.text == "📊 Статистика")
async def admin_stats(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа")
        return
    
    users = get_total_users()
    plugins = get_all_plugins()
    total_downloads = sum(p[5] for p in plugins)
    tickets = len(get_all_open_tickets())
    categories = len(get_categories())
    
    text = f"📊 **Статистика RWPlugins**\n\n"
    text += f"👥 Пользователей: {users}\n"
    text += f"📦 Плагинов: {len(plugins)}\n"
    text += f"📁 Категорий: {categories}\n"
    text += f"⬇️ Всего скачиваний: {total_downloads}\n"
    text += f"🎫 Активных тикетов: {tickets}\n"
    text += f"👑 Владельцев: {len(OWNERS)}\n"
    text += f"👥 Администраторов: {len(get_admins())}\n"
    text += f"📅 Магазин работает с {SHOP_CREATION_DATE}"
    
    await message.answer(text, reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "📈 Рейтинг плагинов")
async def admin_rating(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа")
        return
    
    plugins = get_all_plugins()
    if not plugins:
        await message.answer("📭 Нет плагинов для рейтинга.")
        return
    
    plugins_with_rating = []
    for pid, name, cat_id, price, desc, downloads, rating_sum, rating_count in plugins:
        rating, count = get_plugin_rating(pid)
        plugins_with_rating.append((name, rating, downloads, count))
    
    plugins_with_rating.sort(key=lambda x: x[1], reverse=True)
    
    text = "🏆 **Топ плагинов по рейтингу:**\n\n"
    for i, (name, rating, downloads, count) in enumerate(plugins_with_rating[:10], 1):
        stars = "⭐" * int(rating)
        text += f"{i}. **{name}**\n   🌟 {rating} {stars}\n   ⬇️ {downloads} скачиваний\n   📊 {count} оценок\n\n"
    
    await message.answer(text, reply_markup=get_admin_panel_keyboard())

# ---------- ЗАПУСК ----------
async def main():
    print("🚀 ЗАПУСК RWPlugins БОТА...")
    init_db()
    
    # Добавляем начальные категории
    add_category("Сборки")
    add_category("PvP")
    add_category("Экономика")
    add_category("Боссы")
    
    print(f"✅ Бот RWPlugins успешно запущен!")
    print(f"👑 Владельцы: {OWNERS}")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
