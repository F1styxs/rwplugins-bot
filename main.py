import asyncio
import os
import sqlite3
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# Отключаем лишние логи
logging.getLogger("aiogram.event").setLevel(logging.WARNING)
logging.getLogger("aiogram").setLevel(logging.WARNING)
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNERS = [7130414548]
SHOP_CREATION_DATE = "15.04.2025"

if not BOT_TOKEN:
    print("Токен не найден!")
    exit(1)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Состояния
class UploadPlugin(StatesGroup):
    waiting_for_file = State()
    waiting_for_name = State()
    waiting_for_category = State()
    waiting_for_description = State()

class TicketStates(StatesGroup):
    waiting_for_question = State()
    admin_waiting_for_reply = State()
    admin_waiting_for_ticket_selection = State()

class RatingStates(StatesGroup):
    waiting_for_rating = State()
    waiting_for_review = State()

# Инициализация БД
def init_db():
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE)')
    cur.execute('CREATE TABLE IF NOT EXISTS plugins (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, category_id INTEGER, description TEXT, file_path TEXT, downloads_count INTEGER DEFAULT 0, rating_sum INTEGER DEFAULT 0, rating_count INTEGER DEFAULT 0)')
    cur.execute('CREATE TABLE IF NOT EXISTS reviews (id INTEGER PRIMARY KEY AUTOINCREMENT, plugin_id INTEGER, user_id INTEGER, username TEXT, rating INTEGER, review TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    cur.execute('CREATE TABLE IF NOT EXISTS tickets (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, question TEXT, answer TEXT, status TEXT DEFAULT "open", created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    cur.execute('CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, added_by INTEGER, added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    cur.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, total_downloads INTEGER DEFAULT 0)')
    conn.commit()
    conn.close()
    print("База данных готова")

def register_user(user_id, username):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
    cur.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
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

def add_plugin(name, category_id, description, file_path):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute('INSERT INTO plugins (name, category_id, description, file_path) VALUES (?, ?, ?, ?)', (name, category_id, description, file_path))
    conn.commit()
    conn.close()

def get_plugins_by_category(category_id):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute('SELECT id, name, description, file_path, downloads_count, rating_sum, rating_count FROM plugins WHERE category_id = ?', (category_id,))
    data = cur.fetchall()
    conn.close()
    return data

def get_all_plugins():
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute('SELECT id, name, category_id, description, downloads_count, rating_sum, rating_count FROM plugins')
    data = cur.fetchall()
    conn.close()
    return data

def get_plugin_by_id(plugin_id):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute('SELECT id, name, description, file_path, downloads_count, rating_sum, rating_count FROM plugins WHERE id = ?', (plugin_id,))
    data = cur.fetchone()
    conn.close()
    return data

def delete_plugin(plugin_id):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("DELETE FROM plugins WHERE id = ?", (plugin_id,))
    conn.commit()
    conn.close()

def increment_downloads(plugin_id, user_id):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("UPDATE plugins SET downloads_count = downloads_count + 1 WHERE id = ?", (plugin_id,))
    cur.execute("UPDATE users SET total_downloads = total_downloads + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def add_rating_and_review(plugin_id, user_id, username, rating, review):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT id FROM reviews WHERE plugin_id = ? AND user_id = ?", (plugin_id, user_id))
    if cur.fetchone():
        conn.close()
        return False
    cur.execute("INSERT INTO reviews (plugin_id, user_id, username, rating, review) VALUES (?, ?, ?, ?, ?)", (plugin_id, user_id, username, rating, review))
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

def get_plugin_reviews(plugin_id):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT username, rating, review, created_at FROM reviews WHERE plugin_id = ? ORDER BY created_at DESC LIMIT 10", (plugin_id,))
    data = cur.fetchall()
    conn.close()
    return data

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

def add_message_to_ticket(ticket_id, message, is_admin):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("UPDATE tickets SET answer = ? WHERE id = ?", (message, ticket_id))
    conn.commit()
    conn.close()

def close_ticket(ticket_id):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("UPDATE tickets SET status = 'closed' WHERE id = ?", (ticket_id,))
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

def get_user_info(user_id):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT username, join_date, total_downloads FROM users WHERE user_id = ?", (user_id,))
    data = cur.fetchone()
    conn.close()
    return data

def get_total_users():
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    total = cur.fetchone()[0]
    conn.close()
    return total

# Клавиатуры
def get_main_keyboard():
    kb = [
        [KeyboardButton(text="Категории"), KeyboardButton(text="Список плагинов")],
        [KeyboardButton(text="О магазине"), KeyboardButton(text="Мой профиль")],
        [KeyboardButton(text="Правила"), KeyboardButton(text="Поддержка")],
        [KeyboardButton(text="Оценить плагин")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_admin_keyboard():
    kb = [
        [KeyboardButton(text="Категории"), KeyboardButton(text="Список плагинов")],
        [KeyboardButton(text="О магазине"), KeyboardButton(text="Мой профиль")],
        [KeyboardButton(text="Правила"), KeyboardButton(text="Поддержка")],
        [KeyboardButton(text="Оценить плагин"), KeyboardButton(text="Админ-панель")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_admin_panel_keyboard():
    kb = [
        [KeyboardButton(text="Загрузить плагин")],
        [KeyboardButton(text="Добавить категорию"), KeyboardButton(text="Удалить категорию")],
        [KeyboardButton(text="Удалить плагин")],
        [KeyboardButton(text="Управление админами"), KeyboardButton(text="Управление владельцами")],
        [KeyboardButton(text="Статистика"), KeyboardButton(text="Тикеты")],
        [KeyboardButton(text="Рейтинг плагинов"), KeyboardButton(text="Назад в меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def back_keyboard():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Назад в меню")]], resize_keyboard=True)

def rating_keyboard(plugin_name):
    kb = [
        [KeyboardButton(text="1"), KeyboardButton(text="2"), KeyboardButton(text="3")],
        [KeyboardButton(text="4"), KeyboardButton(text="5")],
        [KeyboardButton(text="Назад в меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# Обработчики
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.full_name or message.from_user.username or str(user_id)
    register_user(user_id, username)
    
    if is_admin(user_id):
        await message.answer(f"Добро пожаловать в RWPlugins!\nВаша роль: {'Владелец' if user_id in OWNERS else 'Администратор'}", reply_markup=get_admin_keyboard())
    else:
        await message.answer("Добро пожаловать в RWPlugins!\nИспользуйте кнопки для навигации.", reply_markup=get_main_keyboard())

@dp.message(F.text == "Назад в меню")
async def back_to_menu(message: types.Message):
    user_id = message.from_user.id
    if is_admin(user_id):
        await message.answer("Главное меню", reply_markup=get_admin_keyboard())
    else:
        await message.answer("Главное меню", reply_markup=get_main_keyboard())

@dp.message(F.text == "Админ-панель")
async def open_admin_panel(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("Нет доступа к админ-панели!", reply_markup=get_main_keyboard())
        return
    await message.answer("Панель администратора", reply_markup=get_admin_panel_keyboard())

# Категории
@dp.message(F.text == "Категории")
async def show_categories(message: types.Message):
    cats = get_categories()
    if not cats:
        await message.answer("Категорий пока нет.", reply_markup=back_keyboard())
        return
    text = "Категории товаров:\n\n"
    kb = []
    for cat_id, cat_name in cats:
        text += f"• {cat_name}\n"
        kb.append([KeyboardButton(text=f"Плагины {cat_name}")])
    kb.append([KeyboardButton(text="Назад в меню")])
    await message.answer(text, reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))

@dp.message(F.text.startswith("Плагины "))
async def show_plugins_in_category(message: types.Message):
    cat_name = message.text.replace("Плагины ", "")
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT id FROM categories WHERE name = ?", (cat_name,))
    cat = cur.fetchone()
    if not cat:
        await message.answer("Категория не найдена")
        return
    plugins = get_plugins_by_category(cat[0])
    conn.close()
    if not plugins:
        await message.answer("В этой категории пока нет плагинов.", reply_markup=back_keyboard())
        return
    text = f"Плагины в категории {cat_name}:\n\n"
    kb = []
    for pid, name, desc, fpath, downloads, rating_sum, rating_count in plugins:
        rating, count = get_plugin_rating(pid)
        stars = "⭐" * int(rating) if rating > 0 else "Нет оценок"
        text += f"• {name}\n  Скачиваний: {downloads}\n  Рейтинг: {rating} {stars}\n  {desc}\n\n"
        kb.append([KeyboardButton(text=f"Скачать {name}")])
        kb.append([KeyboardButton(text=f"Отзывы {name}")])
    kb.append([KeyboardButton(text="Назад в меню")])
    await message.answer(text, reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))

# Список плагинов
@dp.message(F.text == "Список плагинов")
async def all_plugins(message: types.Message):
    plugins = get_all_plugins()
    if not plugins:
        await message.answer("Плагинов пока нет.", reply_markup=back_keyboard())
        return
    text = "Все плагины:\n\n"
    kb = []
    for pid, name, cat_id, desc, downloads, rating_sum, rating_count in plugins:
        rating, count = get_plugin_rating(pid)
        stars = "⭐" * int(rating) if rating > 0 else "Нет оценок"
        text += f"• {name}\n  Скачиваний: {downloads}\n  Рейтинг: {rating} {stars}\n  {desc}\n\n"
        kb.append([KeyboardButton(text=f"Скачать {name}")])
        kb.append([KeyboardButton(text=f"Отзывы {name}")])
    kb.append([KeyboardButton(text="Назад в меню")])
    await message.answer(text, reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))

# Скачивание
@dp.message(F.text.startswith("Скачать "))
async def download_plugin(message: types.Message):
    plugin_name = message.text.replace("Скачать ", "")
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT id, file_path, name FROM plugins WHERE name = ?", (plugin_name,))
    res = cur.fetchone()
    conn.close()
    if not res:
        await message.answer("Плагин не найден")
        return
    plugin_id, file_path, name = res
    if os.path.exists(file_path):
        increment_downloads(plugin_id, message.from_user.id)
        doc = FSInputFile(file_path)
        await message.answer_document(doc, caption=f"Плагин {name} успешно скачан!")
        await message.answer("Понравился плагин? Оцени его в разделе Оценить плагин!")
    else:
        await message.answer("Файл временно недоступен.")

# Отзывы
@dp.message(F.text.startswith("Отзывы "))
async def show_reviews(message: types.Message):
    plugin_name = message.text.replace("Отзывы ", "")
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT id FROM plugins WHERE name = ?", (plugin_name,))
    res = cur.fetchone()
    conn.close()
    if not res:
        await message.answer("Плагин не найден")
        return
    plugin_id = res[0]
    reviews = get_plugin_reviews(plugin_id)
    rating, count = get_plugin_rating(plugin_id)
    if not reviews:
        await message.answer(f"У плагина {plugin_name} пока нет отзывов.\nСредний рейтинг: {rating} ⭐ ({count} оценок)")
        return
    text = f"Отзывы о плагине {plugin_name}:\nСредний рейтинг: {rating} ⭐ ({count} оценок)\n\n"
    for username, rating, review, created_at in reviews:
        stars = "⭐" * rating
        text += f"• {username}\n  Оценка: {rating} {stars}\n  Отзыв: {review}\n  Дата: {created_at[:10]}\n\n"
    await message.answer(text[:4000], reply_markup=back_keyboard())

# Оценка плагина
@dp.message(F.text == "Оценить плагин")
async def rate_plugin_menu(message: types.Message):
    plugins = get_all_plugins()
    if not plugins:
        await message.answer("Нет плагинов для оценки.", reply_markup=back_keyboard())
        return
    kb = []
    for pid, name, cat_id, desc, downloads, rating_sum, rating_count in plugins:
        kb.append([KeyboardButton(text=f"Оценить {name}")])
    kb.append([KeyboardButton(text="Назад в меню")])
    await message.answer("Выберите плагин для оценки:", reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))

@dp.message(F.text.startswith("Оценить "))
async def start_rating(message: types.Message, state: FSMContext):
    plugin_name = message.text.replace("Оценить ", "")
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT id FROM plugins WHERE name = ?", (plugin_name,))
    res = cur.fetchone()
    conn.close()
    if not res:
        await message.answer("Плагин не найден")
        return
    plugin_id = res[0]
    await state.update_data(plugin_id=plugin_id, plugin_name=plugin_name)
    await message.answer(f"Оцените плагин {plugin_name} от 1 до 5:", reply_markup=rating_keyboard(plugin_name))
    await state.set_state(RatingStates.waiting_for_rating)

@dp.message(RatingStates.waiting_for_rating, F.text.in_(["1", "2", "3", "4", "5"]))
async def process_rating(message: types.Message, state: FSMContext):
    rating = int(message.text)
    data = await state.get_data()
    plugin_id = data.get("plugin_id")
    plugin_name = data.get("plugin_name")
    await state.update_data(rating=rating)
    await message.answer("Напишите ваш отзыв о плагине (текстом):")
    await state.set_state(RatingStates.waiting_for_review)

@dp.message(RatingStates.waiting_for_review, F.text)
async def process_review(message: types.Message, state: FSMContext):
    review = message.text
    data = await state.get_data()
    plugin_id = data.get("plugin_id")
    plugin_name = data.get("plugin_name")
    rating = data.get("rating")
    user_id = message.from_user.id
    username = message.from_user.full_name or message.from_user.username or str(user_id)
    if add_rating_and_review(plugin_id, user_id, username, rating, review):
        rating_val, count = get_plugin_rating(plugin_id)
        await message.answer(f"Спасибо за оценку!\nСредний рейтинг плагина {plugin_name}: {rating_val} ⭐ ({count} оценок)", reply_markup=get_main_keyboard() if not is_admin(user_id) else get_admin_keyboard())
    else:
        await message.answer("Вы уже оценивали этот плагин!", reply_markup=get_main_keyboard() if not is_admin(user_id) else get_admin_keyboard())
    await state.clear()

# Информационные кнопки
@dp.message(F.text == "О магазине")
async def about_shop(message: types.Message):
    text = f"RWPlugins - Ключ к созданию большего!\n\nМы создаём качественные плагины для Minecraft.\nМагазин работает с {SHOP_CREATION_DATE}\n\nПо вопросам: @nnxHub | @Sartexa"
    await message.answer(text, reply_markup=back_keyboard())

@dp.message(F.text == "Мой профиль")
async def profile(message: types.Message):
    user_id = message.from_user.id
    user_info = get_user_info(user_id)
    username = user_info[0] if user_info else message.from_user.full_name
    join_date = user_info[1] if user_info else datetime.now()
    downloads = user_info[2] if user_info else 0
    role = "Владелец" if user_id in OWNERS else "Администратор" if is_admin(user_id) else "Участник"
    text = f"Мой профиль\n\nИмя: {username}\nID: {user_id}\nРоль: {role}\nДата регистрации: {join_date[:10] if join_date else datetime.now().strftime('%Y-%m-%d')}\nСкачиваний: {downloads}"
    await message.answer(text, reply_markup=back_keyboard())

@dp.message(F.text == "Правила")
async def rules(message: types.Message):
    text = "Правила магазина RWPlugins\n\n1. Запрещён возврат средств после скачивания\n2. Все плагины проверены\n3. Техподдержка отвечает в течение 24 часов\n4. Запрещено распространять плагины"
    await message.answer(text, reply_markup=back_keyboard())

# Поддержка (тикеты с перепиской)
@dp.message(F.text == "Поддержка")
async def support_start(message: types.Message, state: FSMContext):
    existing_ticket = get_user_ticket(message.from_user.id)
    if existing_ticket:
        ticket_id, question, answer, status, created_at = existing_ticket
        kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Добавить сообщение в тикет")], [KeyboardButton(text="Назад в меню")]], resize_keyboard=True)
        await message.answer(f"У вас уже есть активный тикет #{ticket_id}!\nВопрос: {question}\n\nОжидайте ответа администратора или добавьте новое сообщение.", reply_markup=kb)
        await state.set_state(TicketStates.waiting_for_question)
        return
    await message.answer("Создать тикет?\n\nНапишите ваш вопрос подробно. Администратор ответит вам в этом чате.\n\nЕсли передумали - нажмите Назад в меню.")
    await state.set_state(TicketStates.waiting_for_question)

@dp.message(TicketStates.waiting_for_question, F.text)
async def create_ticket_handler(message: types.Message, state: FSMContext):
    if message.text == "Назад в меню":
        await state.clear()
        await back_to_menu(message)
        return
    ticket_id = create_ticket(message.from_user.id, message.text)
    await message.answer(f"Тикет #{ticket_id} создан!\n\nАдминистратор ответит вам здесь. Ожидайте.", reply_markup=get_main_keyboard() if not is_admin(message.from_user.id) else get_admin_keyboard())
    await state.clear()
    for admin_id in OWNERS:
        try:
            await bot.send_message(admin_id, f"Новый тикет #{ticket_id}\nОт: {message.from_user.id}\nВопрос: {message.text[:100]}")
        except:
            pass
    for admin_id, _, _ in get_admins():
        try:
            await bot.send_message(admin_id, f"Новый тикет #{ticket_id}\nОт: {message.from_user.id}\nВопрос: {message.text[:100]}")
        except:
            pass

@dp.message(F.text == "Добавить сообщение в тикет")
async def add_to_ticket(message: types.Message, state: FSMContext):
    ticket = get_user_ticket(message.from_user.id)
    if not ticket:
        await message.answer("У вас нет активных тикетов.")
        return
    ticket_id = ticket[0]
    await state.update_data(ticket_id=ticket_id)
    await message.answer("Напишите новое сообщение для поддержки:")
    await state.set_state("waiting_for_ticket_message")

@dp.message(StateFilter("waiting_for_ticket_message"), F.text)
async def process_ticket_message(message: types.Message, state: FSMContext):
    data = await state.get_data()
    ticket_id = data.get("ticket_id")
    add_message_to_ticket(ticket_id, message.text, False)
    await message.answer("Сообщение добавлено в тикет! Администратор ответит вам.", reply_markup=get_main_keyboard() if not is_admin(message.from_user.id) else get_admin_keyboard())
    for admin_id in OWNERS:
        try:
            await bot.send_message(admin_id, f"Новое сообщение в тикете #{ticket_id}\nОт: {message.from_user.id}\nСообщение: {message.text[:100]}")
        except:
            pass
    for admin_id, _, _ in get_admins():
        try:
            await bot.send_message(admin_id, f"Новое сообщение в тикете #{ticket_id}\nОт: {message.from_user.id}\nСообщение: {message.text[:100]}")
        except:
            pass
    await state.clear()

# Админ: тикеты
@dp.message(F.text == "Тикеты")
async def admin_view_tickets(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("Нет доступа")
        return
    tickets = get_all_open_tickets()
    if not tickets:
        await message.answer("Нет активных тикетов.", reply_markup=get_admin_panel_keyboard())
        return
    text = "Активные тикеты:\n\n"
    kb = []
    for ticket_id, user_id, question, created_at in tickets:
        text += f"#{ticket_id} | От: {user_id}\n{question[:50]}...\n\n"
        kb.append([KeyboardButton(text=f"Ответить в тикет #{ticket_id}")])
        kb.append([KeyboardButton(text=f"Закрыть тикет #{ticket_id}")])
    kb.append([KeyboardButton(text="Назад в меню")])
    await message.answer(text, reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))
    await state.set_state(TicketStates.admin_waiting_for_ticket_selection)

@dp.message(TicketStates.admin_waiting_for_ticket_selection, F.text.startswith("Ответить в тикет #"))
async def admin_reply_to_ticket(message: types.Message, state: FSMContext):
    ticket_id = int(message.text.split("#")[1])
    ticket = get_ticket_by_id(ticket_id)
    if not ticket:
        await message.answer("Тикет не найден")
        await state.clear()
        return
    await state.update_data(ticket_id=ticket_id, user_id=ticket[1])
    await message.answer(f"Введите ответ для пользователя (тикет #{ticket_id}):\n\nВопрос: {ticket[2]}")
    await state.set_state(TicketStates.admin_waiting_for_reply)

@dp.message(TicketStates.admin_waiting_for_reply, F.text)
async def admin_send_reply(message: types.Message, state: FSMContext):
    data = await state.get_data()
    ticket_id = data.get("ticket_id")
    user_id = data.get("user_id")
    answer = message.text
    add_message_to_ticket(ticket_id, f"Администратор: {answer}", True)
    try:
        await bot.send_message(user_id, f"Ответ поддержки (тикет #{ticket_id})\n\n{answer}\n\nЧтобы ответить - нажмите Добавить сообщение в тикет")
    except:
        pass
    await message.answer(f"Ответ отправлен пользователю {user_id}.")
    await state.clear()
    await message.answer("Админ-панель", reply_markup=get_admin_panel_keyboard())

@dp.message(TicketStates.admin_waiting_for_ticket_selection, F.text.startswith("Закрыть тикет #"))
async def admin_close_ticket(message: types.Message):
    ticket_id = int(message.text.split("#")[1])
    ticket = get_ticket_by_id(ticket_id)
    if ticket:
        close_ticket(ticket_id)
        try:
            await bot.send_message(ticket[1], f"Ваш тикет #{ticket_id} закрыт администратором. Спасибо за обращение!")
        except:
            pass
        await message.answer(f"Тикет #{ticket_id} закрыт.")
    else:
        await message.answer("Тикет не найден")
    await message.answer("Админ-панель", reply_markup=get_admin_panel_keyboard())

# Админ: загрузка плагина
@dp.message(F.text == "Загрузить плагин")
async def admin_upload_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("Нет доступа")
        return
    await message.answer("Отправьте файл плагина (zip, py, jar):")
    await state.set_state(UploadPlugin.waiting_for_file)

@dp.message(StateFilter(UploadPlugin.waiting_for_file), F.document)
async def get_plugin_file(message: types.Message, state: FSMContext):
    doc = message.document
    file_path = f"plugins/{doc.file_name}"
    os.makedirs("plugins", exist_ok=True)
    file = await bot.get_file(doc.file_id)
    await bot.download_file(file.file_path, file_path)
    await state.update_data(file_path=file_path)
    await message.answer("Введите название плагина:")
    await state.set_state(UploadPlugin.waiting_for_name)

@dp.message(StateFilter(UploadPlugin.waiting_for_name), F.text)
async def get_plugin_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    cats = get_categories()
    if not cats:
        await message.answer("Сначала создайте категорию!")
        await state.clear()
        return
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=cat_name)] for _, cat_name in cats], resize_keyboard=True)
    await message.answer("Выберите категорию:", reply_markup=kb)
    await state.set_state(UploadPlugin.waiting_for_category)

@dp.message(StateFilter(UploadPlugin.waiting_for_category), F.text)
async def get_plugin_category(message: types.Message, state: FSMContext):
    cat_name = message.text
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT id FROM categories WHERE name = ?", (cat_name,))
    cat = cur.fetchone()
    conn.close()
    if not cat:
        await message.answer("Категория не найдена!")
        return
    await state.update_data(category_id=cat[0])
    await message.answer("Введите описание плагина:")
    await state.set_state(UploadPlugin.waiting_for_description)

@dp.message(StateFilter(UploadPlugin.waiting_for_description), F.text)
async def finish_upload(message: types.Message, state: FSMContext):
    data = await state.get_data()
    add_plugin(data['name'], data['category_id'], data['description'], data['file_path'])
    await message.answer(f"Плагин {data['name']} добавлен!", reply_markup=get_admin_panel_keyboard())
    await state.clear()

# Админ: категории
@dp.message(F.text == "Добавить категорию")
async def admin_add_category_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("Нет доступа")
        return
    await message.answer("Введите название новой категории:")
    await state.set_state("waiting_for_category")

@dp.message(StateFilter("waiting_for_category"), F.text)
async def admin_add_category(message: types.Message, state: FSMContext):
    add_category(message.text)
    await message.answer(f"Категория {message.text} добавлена!", reply_markup=get_admin_panel_keyboard())
    await state.clear()

@dp.message(F.text == "Удалить категорию")
async def admin_del_category_menu(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("Нет доступа")
        return
    cats = get_categories()
    if not cats:
        await message.answer("Нет категорий для удаления.")
        return
    kb = [[KeyboardButton(text=f"Удалить категорию {cat_name}")] for _, cat_name in cats]
    kb.append([KeyboardButton(text="Назад в меню")])
    await message.answer("Выберите категорию для удаления:", reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))

@dp.message(F.text.startswith("Удалить категорию "))
async def confirm_delete_category(message: types.Message):
    cat_name = message.text.replace("Удалить категорию ", "")
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT id FROM categories WHERE name = ?", (cat_name,))
    cat_id = cur.fetchone()
    conn.close()
    if cat_id:
        delete_category(cat_id[0])
        await message.answer(f"Категория {cat_name} удалена!")
    else:
        await message.answer("Категория не найдена")
    await message.answer("Админ-панель", reply_markup=get_admin_panel_keyboard())

# Админ: удаление плагина
@dp.message(F.text == "Удалить плагин")
async def admin_del_plugin_menu(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("Нет доступа")
        return
    plugins = get_all_plugins()
    if not plugins:
        await message.answer("Нет плагинов для удаления.")
        return
    kb = [[KeyboardButton(text=f"Удалить плагин {name}")] for pid, name, cat_id, desc, downloads, rating_sum, rating_count in plugins]
    kb.append([KeyboardButton(text="Назад в меню")])
    await message.answer("Выберите плагин для удаления:", reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))

@dp.message(F.text.startswith("Удалить плагин "))
async def confirm_delete_plugin(message: types.Message):
    plugin_name = message.text.replace("Удалить плагин ", "")
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT id FROM plugins WHERE name = ?", (plugin_name,))
    plugin = cur.fetchone()
    conn.close()
    if plugin:
        delete_plugin(plugin[0])
        await message.answer(f"Плагин {plugin_name} удалён!")
    else:
        await message.answer("Плагин не найден")
    await message.answer("Админ-панель", reply_markup=get_admin_panel_keyboard())

# Админ: управление админами
@dp.message(F.text == "Управление админами")
async def admin_manage_admins(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("Нет доступа")
        return
    kb = [
        [KeyboardButton(text="Добавить админа")],
        [KeyboardButton(text="Удалить админа")],
        [KeyboardButton(text="Список админов")],
        [KeyboardButton(text="Назад в меню")]
    ]
    await message.answer("Управление администраторами", reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))

@dp.message(F.text == "Добавить админа")
async def add_admin_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in OWNERS:
        await message.answer("Только владельцы могут добавлять админов!")
        return
    await message.answer("Введите Telegram ID пользователя:")
    await state.set_state("waiting_for_admin_id")

@dp.message(StateFilter("waiting_for_admin_id"), F.text)
async def add_admin_process(message: types.Message, state: FSMContext):
    try:
        admin_id = int(message.text)
        if admin_id in OWNERS:
            await message.answer("Этот пользователь уже владелец!")
        else:
            add_admin(admin_id, message.from_user.id)
            await message.answer(f"Пользователь {admin_id} теперь администратор!")
    except:
        await message.answer("Неверный ID!")
    await state.clear()
    await message.answer("Админ-панель", reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "Удалить админа")
async def remove_admin_menu(message: types.Message):
    if message.from_user.id not in OWNERS:
        await message.answer("Только владельцы могут удалять админов!")
        return
    admins = get_admins()
    if not admins:
        await message.answer("Нет администраторов для удаления.")
        return
    kb = [[KeyboardButton(text=f"Удалить админа {admin_id}")] for admin_id, _, _ in admins]
    kb.append([KeyboardButton(text="Назад в меню")])
    await message.answer("Выберите администратора для удаления:", reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))

@dp.message(F.text.startswith("Удалить админа "))
async def remove_admin_process(message: types.Message):
    try:
        admin_id = int(message.text.replace("Удалить админа ", ""))
        if admin_id in OWNERS:
            await message.answer("Нельзя удалить владельца!")
            return
        remove_admin(admin_id)
        await message.answer(f"Администратор {admin_id} удалён!")
    except:
        await message.answer("Ошибка!")
    await message.answer("Админ-панель", reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "Список админов")
async def list_admins(message: types.Message):
    admins = get_admins()
    text = "Владельцы:\n"
    for owner_id in OWNERS:
        text += f"• {owner_id}\n"
    text += "\nАдминистраторы:\n"
    if admins:
        for admin_id, added_by, added_at in admins:
            text += f"• {admin_id} (добавлен {added_at[:10]})\n"
    else:
        text += "Нет администраторов\n"
    await message.answer(text, reply_markup=get_admin_panel_keyboard())

# Админ: управление владельцами
@dp.message(F.text == "Управление владельцами")
async def owner_manage(message: types.Message):
    if message.from_user.id not in OWNERS:
        await message.answer("Только владельцы могут управлять владельцами!")
        return
    kb = [
        [KeyboardButton(text="Добавить владельца")],
        [KeyboardButton(text="Список владельцев")],
        [KeyboardButton(text="Назад в меню")]
    ]
    await message.answer("Управление владельцами", reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))

@dp.message(F.text == "Добавить владельца")
async def add_owner_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in OWNERS:
        await message.answer("Нет прав!")
        return
    await message.answer("Введите Telegram ID нового владельца:")
    await state.set_state("waiting_for_owner_id")

@dp.message(StateFilter("waiting_for_owner_id"), F.text)
async def add_owner_process(message: types.Message, state: FSMContext):
    try:
        owner_id = int(message.text)
        if owner_id not in OWNERS:
            OWNERS.append(owner_id)
            await message.answer(f"Пользователь {owner_id} теперь владелец!")
        else:
            await message.answer("Пользователь уже владелец!")
    except:
        await message.answer("Неверный ID!")
    await state.clear()
    await message.answer("Админ-панель", reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "Список владельцев")
async def list_owners(message: types.Message):
    text = "Список владельцев:\n\n"
    for owner_id in OWNERS:
        text += f"• {owner_id}\n"
    await message.answer(text, reply_markup=get_admin_panel_keyboard())

# Админ: статистика и рейтинг
@dp.message(F.text == "Статистика")
async def admin_stats(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("Нет доступа")
        return
    users = get_total_users()
    plugins = get_all_plugins()
    total_downloads = sum(p[4] for p in plugins)
    tickets = len(get_all_open_tickets())
    categories = len(get_categories())
    text = f"Статистика RWPlugins\n\nПользователей: {users}\nПлагинов: {len(plugins)}\nКатегорий: {categories}\nВсего скачиваний: {total_downloads}\nАктивных тикетов: {tickets}\nВладельцев: {len(OWNERS)}\nАдминистраторов: {len(get_admins())}\nМагазин работает с {SHOP_CREATION_DATE}"
    await message.answer(text, reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "Рейтинг плагинов")
async def admin_rating(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("Нет доступа")
        return
    plugins = get_all_plugins()
    if not plugins:
        await message.answer("Нет плагинов для рейтинга.")
        return
    plugins_with_rating = []
    for pid, name, cat_id, desc, downloads, rating_sum, rating_count in plugins:
        rating, count = get_plugin_rating(pid)
        plugins_with_rating.append((name, rating, downloads, count))
    plugins_with_rating.sort(key=lambda x: x[1], reverse=True)
    text = "Топ плагинов по рейтингу:\n\n"
    for i, (name, rating, downloads, count) in enumerate(plugins_with_rating[:10], 1):
        stars = "⭐" * int(rating)
        text += f"{i}. {name}\n   Рейтинг: {rating} {stars}\n   Скачиваний: {downloads}\n   Оценок: {count}\n\n"
    await message.answer(text, reply_markup=get_admin_panel_keyboard())

# Запуск
async def main():
    print("Запуск RWPlugins бота...")
    init_db()
    add_category("Сборки")
    add_category("PvP")
    add_category("Экономика")
    add_category("Боссы")
    print("Бот успешно запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
