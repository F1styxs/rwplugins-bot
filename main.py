import asyncio
import os
import sqlite3
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# Отключаем обработку сигналов для совместимости с Render
import signal
signal.signal(signal.SIGTERM, signal.SIG_IGN)

# Настройки
logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = 7130414548  # ТВОЙ ID

# Проверка наличия токена
if not BOT_TOKEN:
    print("❌ ОШИБКА: BOT_TOKEN не найден в переменных окружения!")
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

class TicketQuestion(StatesGroup):
    waiting_for_question = State()

# ---------- БД ----------
def init_db():
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS plugins (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, category_id INTEGER, description TEXT, price INTEGER DEFAULT 0, file_path TEXT, downloads_count INTEGER DEFAULT 0)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS tickets (user_id INTEGER PRIMARY KEY, question TEXT, status TEXT DEFAULT 'open', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, added_by INTEGER, added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, total_downloads INTEGER DEFAULT 0)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS downloads_stats (id INTEGER PRIMARY KEY AUTOINCREMENT, plugin_id INTEGER, user_id INTEGER, downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()
    print("✅ База данных готова")

def register_user(user_id):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def get_user_stats(user_id):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT join_date, total_downloads FROM users WHERE user_id = ?", (user_id,))
    res = cur.fetchone()
    conn.close()
    if res:
        return res
    return (datetime.now(), 0)

def update_user_downloads(user_id):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("UPDATE users SET total_downloads = total_downloads + 1 WHERE user_id = ?", (user_id,))
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
    cur.execute('INSERT INTO plugins (name, category_id, price, description, file_path, downloads_count) VALUES (?, ?, ?, ?, ?, 0)', (name, category_id, price, description, file_path))
    conn.commit()
    conn.close()

def get_plugins_by_category(category_id, page=1, per_page=5):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    offset = (page - 1) * per_page
    cur.execute('SELECT id, name, description, price, file_path, downloads_count FROM plugins WHERE category_id = ? LIMIT ? OFFSET ?', (category_id, per_page, offset))
    data = cur.fetchall()
    cur.execute("SELECT COUNT(*) FROM plugins WHERE category_id = ?", (category_id,))
    total = cur.fetchone()[0]
    conn.close()
    return data, total

def get_all_plugins(page=1, per_page=5):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    offset = (page - 1) * per_page
    cur.execute('SELECT p.id, p.name, c.name, p.price, p.description, p.downloads_count FROM plugins p JOIN categories c ON p.category_id = c.id LIMIT ? OFFSET ?', (per_page, offset))
    data = cur.fetchall()
    cur.execute("SELECT COUNT(*) FROM plugins")
    total = cur.fetchone()[0]
    conn.close()
    return data, total

def increment_downloads(plugin_id, user_id):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("UPDATE plugins SET downloads_count = downloads_count + 1 WHERE id = ?", (plugin_id,))
    cur.execute("INSERT INTO downloads_stats (plugin_id, user_id, downloaded_at) VALUES (?, ?, ?)", (plugin_id, user_id, datetime.now()))
    conn.commit()
    conn.close()
    update_user_downloads(user_id)

def get_plugin_stats(plugin_id):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT downloads_count FROM plugins WHERE id = ?", (plugin_id,))
    total = cur.fetchone()
    conn.close()
    if total:
        return total[0]
    return 0

def create_ticket(user_id, question):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("REPLACE INTO tickets (user_id, question, status) VALUES (?, ?, 'open')", (user_id, question))
    conn.commit()
    conn.close()

def close_ticket(user_id):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("DELETE FROM tickets WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def is_ticket_open(user_id):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT status FROM tickets WHERE user_id = ?", (user_id,))
    res = cur.fetchone()
    conn.close()
    return res is not None

def get_all_tickets():
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT user_id, question, created_at FROM tickets WHERE status = 'open'")
    data = cur.fetchall()
    conn.close()
    return data

def is_admin(user_id):
    if user_id == OWNER_ID:
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

# ---------- КЛАВИАТУРЫ ----------
def main_menu():
    kb = [
        [InlineKeyboardButton(text="📂 Категории", callback_data="categories")],
        [InlineKeyboardButton(text="📋 Список товаров", callback_data="products")],
        [InlineKeyboardButton(text="ℹ️ О магазине", callback_data="about")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile")],
        [InlineKeyboardButton(text="📜 Правила", callback_data="rules")],
        [InlineKeyboardButton(text="🆘 Поддержка", callback_data="support")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def admin_panel_menu():
    kb = [
        [InlineKeyboardButton(text="📥 Загрузить плагин", callback_data="admin_upload")],
        [InlineKeyboardButton(text="➕ Добавить категорию", callback_data="admin_add_category")],
        [InlineKeyboardButton(text="🗑 Удалить категорию", callback_data="admin_del_category")],
        [InlineKeyboardButton(text="👥 Добавить админа", callback_data="admin_add_admin")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🎫 Тикеты", callback_data="admin_tickets")],
        [InlineKeyboardButton(text="📈 Рейтинг", callback_data="admin_rating")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def back_button():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀ Назад", callback_data="main_menu")]
    ])

# ---------- ОСНОВНЫЕ ОБРАБОТЧИКИ ----------
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    register_user(user_id)
    
    menu = main_menu()
    if is_admin(user_id):
        menu.inline_keyboard.append([InlineKeyboardButton(text="⚙️ Админ-панель", callback_data="admin_panel")])
    
    await message.answer(
        "🏪 **RWPlugins - Ключ к созданию большего!**\n\n"
        "Добро пожаловать в магазин плагинов!\n"
        "Используйте кнопки ниже для навигации:",
        reply_markup=menu
    )

@dp.callback_query(F.data == "main_menu")
async def back_to_main(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    menu = main_menu()
    if is_admin(user_id):
        menu.inline_keyboard.append([InlineKeyboardButton(text="⚙️ Админ-панель", callback_data="admin_panel")])
    
    await callback.message.edit_text(
        "🏪 **Главное меню RWPlugins**\n\nВыберите действие:",
        reply_markup=menu
    )

# ---------- КАТЕГОРИИ ----------
@dp.callback_query(F.data == "categories")
async def show_categories(callback: types.CallbackQuery):
    cats = get_categories()
    if not cats:
        await callback.message.edit_text("❌ Категорий пока нет.", reply_markup=back_button())
        return
    kb = []
    for cat_id, cat_name in cats:
        kb.append([InlineKeyboardButton(text=f"📁 {cat_name}", callback_data=f"cat_{cat_id}_1")])
    kb.append([InlineKeyboardButton(text="◀ Назад", callback_data="main_menu")])
    await callback.message.edit_text("📂 **Категории товаров:**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("cat_"))
async def show_plugins(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    cat_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 1
    
    plugins, total = get_plugins_by_category(cat_id, page=page, per_page=5)
    total_pages = (total + 4) // 5
    
    if not plugins:
        await callback.message.edit_text("❌ В этой категории пока нет плагинов.", reply_markup=back_button())
        return
    
    text = f"📁 **Товары в категории:**\n\n"
    for pid, name, desc, price, fpath, downloads in plugins:
        text += f"🔹 **{name}**\n"
        text += f"   💰 Цена: {price} ₽\n"
        text += f"   ⬇️ Скачиваний: {downloads}\n"
        text += f"   📝 {desc}\n\n"
    
    kb = []
    for pid, name, desc, price, fpath, downloads in plugins:
        kb.append([InlineKeyboardButton(text=f"📥 Купить {name} ({price}₽)", callback_data=f"buy_{pid}")])
    
    if total_pages > 1:
        nav_buttons = []
        if page > 1:
            nav_buttons.append(InlineKeyboardButton(text="◀ Пред", callback_data=f"cat_{cat_id}_{page-1}"))
        if page < total_pages:
            nav_buttons.append(InlineKeyboardButton(text="След ▶", callback_data=f"cat_{cat_id}_{page+1}"))
        if nav_buttons:
            kb.append(nav_buttons)
    
    kb.append([InlineKeyboardButton(text="◀ Назад", callback_data="categories")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# ---------- ВСЕ ТОВАРЫ ----------
@dp.callback_query(F.data == "products")
async def all_products(callback: types.CallbackQuery):
    await show_products_page(callback, page=1)

async def show_products_page(callback: types.CallbackQuery, page: int):
    plugins, total = get_all_plugins(page=page, per_page=5)
    total_pages = (total + 4) // 5
    
    if not plugins:
        await callback.message.edit_text("📭 Товаров пока нет.", reply_markup=back_button())
        return
    
    text = "📦 **Все товары RWPlugins:**\n\n"
    for pid, name, cat_name, price, desc, downloads in plugins:
        text += f"🔹 **{name}**\n"
        text += f"   📁 {cat_name}\n"
        text += f"   💰 {price} ₽\n"
        text += f"   ⬇️ {downloads} скачиваний\n"
        text += f"   📝 {desc}\n\n"
    
    kb = []
    for pid, name, cat_name, price, desc, downloads in plugins:
        kb.append([InlineKeyboardButton(text=f"📥 Купить {name} ({price}₽)", callback_data=f"buy_{pid}")])
    
    if total_pages > 1:
        nav_buttons = []
        if page > 1:
            nav_buttons.append(InlineKeyboardButton(text="◀ Пред", callback_data=f"products_page_{page-1}"))
        if page < total_pages:
            nav_buttons.append(InlineKeyboardButton(text="След ▶", callback_data=f"products_page_{page+1}"))
        if nav_buttons:
            kb.append(nav_buttons)
    
    kb.append([InlineKeyboardButton(text="◀ Назад", callback_data="main_menu")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("products_page_"))
async def products_page_callback(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[2])
    await show_products_page(callback, page)

# ---------- ПОКУПКА / СКАЧИВАНИЕ ----------
@dp.callback_query(F.data.startswith("buy_"))
async def buy_plugin(callback: types.CallbackQuery):
    plugin_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT file_path, name, price FROM plugins WHERE id = ?", (plugin_id,))
    res = cur.fetchone()
    conn.close()
    
    if not res:
        await callback.answer("❌ Плагин не найден")
        return
    
    file_path, name, price = res
    
    if os.path.exists(file_path):
        increment_downloads(plugin_id, user_id)
        doc = FSInputFile(file_path)
        await callback.message.answer_document(
            doc, 
            caption=f"✅ **{name}** успешно приобретён!\n"
                    f"💰 Цена: {price} ₽\n"
                    f"⬇️ Всего скачиваний: {get_plugin_stats(plugin_id)}"
        )
    else:
        await callback.message.answer("❌ Файл временно недоступен. Обратитесь в поддержку.")
    await callback.answer()

# ---------- ПРОФИЛЬ ----------
@dp.callback_query(F.data == "profile")
async def show_profile(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    join_date, total_downloads = get_user_stats(user_id)
    
    text = f"👤 **Ваш профиль RWPlugins**\n\n"
    text += f"🆔 ID: {user_id}\n"
    text += f"📅 Дата регистрации: {join_date.strftime('%d.%m.%Y')}\n"
    text += f"⬇️ Всего скачиваний: {total_downloads}\n"
    
    await callback.message.edit_text(text, reply_markup=back_button())

# ---------- ПРАВИЛА ----------
@dp.callback_query(F.data == "rules")
async def show_rules(callback: types.CallbackQuery):
    text = "📜 **Правила магазина RWPlugins**\n\n"
    text += "1. Запрещён возврат средств после скачивания\n"
    text += "2. Все плагины проверены на вирусы\n"
    text += "3. Техподдержка отвечает в течение 24 часов\n"
    text += "4. Запрещено распространять плагины\n"
    text += "5. При нарушении правил - бан без возврата\n\n"
    text += "По всем вопросам: @owner_rwplugins"
    
    await callback.message.edit_text(text, reply_markup=back_button())

# ---------- О МАГАЗИНЕ ----------
@dp.callback_query(F.data == "about")
async def about_shop(callback: types.CallbackQuery):
    text = "🏪 **RWPlugins - Ключ к созданию большего!**\n\n"
    text += "Мы создаём качественные плагины для Minecraft.\n"
    text += "В нашем ассортименте:\n"
    text += "• PvP системы\n"
    text += "• Экономика\n"
    text += "• Босс-арены\n"
    text += "• Кейсы и лутбоксы\n\n"
    text += "💬 По вопросам сотрудничества: @owner_rwplugins"
    
    await callback.message.edit_text(text, reply_markup=back_button())

# ---------- ПОДДЕРЖКА (ТИКЕТЫ) ----------
@dp.callback_query(F.data == "support")
async def support_menu(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✉️ Создать тикет", callback_data="create_ticket")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="main_menu")]
    ])
    await callback.message.edit_text(
        "🆘 **Техническая поддержка RWPlugins**\n\n"
        "Нажмите «Создать тикет», чтобы отправить вопрос.",
        reply_markup=kb
    )

@dp.callback_query(F.data == "create_ticket")
async def start_ticket(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if is_ticket_open(user_id):
        await callback.answer("❌ У вас уже есть активный тикет!")
        return
    await callback.message.edit_text("📝 Напишите ваш вопрос в одном сообщении:")
    await state.set_state(TicketQuestion.waiting_for_question)
    await callback.answer()

@dp.message(StateFilter(TicketQuestion.waiting_for_question), F.text)
async def receive_question(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    question = message.text
    
    create_ticket(user_id, question)
    
    # Отправляем владельцу
    try:
        await bot.send_message(
            OWNER_ID,
            f"🆕 **Новый тикет RWPlugins**\n\n"
            f"👤 От: {message.from_user.full_name}\n"
            f"🆔 ID: {user_id}\n"
            f"📩 Вопрос:\n{question}"
        )
    except:
        pass
    
    # Отправляем всем админам
    for admin_id, _, _ in get_admins():
        try:
            await bot.send_message(
                admin_id,
                f"🆕 **Новый тикет RWPlugins**\n\n"
                f"👤 От: {message.from_user.full_name}\n"
                f"🆔 ID: {user_id}\n"
                f"📩 Вопрос:\n{question}"
            )
        except:
            pass
    
    await message.answer(
        "✅ **Тикет создан!**\n\n"
        "Техподдержка RWPlugins ответит вам в ближайшее время."
    )
    await state.clear()

# ---------- АДМИН-ПАНЕЛЬ ----------
@dp.callback_query(F.data == "admin_panel")
async def admin_panel(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ У вас нет прав администратора!")
        return
    await callback.message.edit_text("⚙️ **Панель администратора RWPlugins**", reply_markup=admin_panel_menu())

# Загрузка плагина
@dp.callback_query(F.data == "admin_upload")
async def admin_upload_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав")
        return
    await callback.message.edit_text("📎 Отправьте файл плагина (zip, py, jar, и т.д.):")
    await state.set_state(UploadPlugin.waiting_for_file)
    await callback.answer()

@dp.message(StateFilter(UploadPlugin.waiting_for_file), F.document)
async def get_plugin_file(message: types.Message, state: FSMContext):
    doc = message.document
    file_name = doc.file_name
    file_path = f"plugins/{file_name}"
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
            await message.answer("⚠️ Сначала создайте категорию в админ-панели")
            await state.clear()
            return
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=cat_name, callback_data=f"upload_cat_{cat_id}")] for cat_id, cat_name in cats
        ])
        await message.answer("📂 Выберите категорию:", reply_markup=kb)
        await state.set_state(UploadPlugin.waiting_for_category)
    except ValueError:
        await message.answer("❌ Введите число (только цифры)!")

@dp.callback_query(StateFilter(UploadPlugin.waiting_for_category), F.data.startswith("upload_cat_"))
async def get_plugin_category(callback: types.CallbackQuery, state: FSMContext):
    cat_id = int(callback.data.split("_")[2])
    await state.update_data(category_id=cat_id)
    await callback.message.answer("📝 Введите **описание** плагина:")
    await state.set_state(UploadPlugin.waiting_for_description)
    await callback.answer()

@dp.message(StateFilter(UploadPlugin.waiting_for_description), F.text)
async def finish_upload(message: types.Message, state: FSMContext):
    data = await state.get_data()
    add_plugin(
        name=data['name'],
        category_id=data['category_id'],
        price=data['price'],
        description=message.text,
        file_path=data['file_path']
    )
    await message.answer(
        f"✅ **Плагин успешно добавлен в RWPlugins!**\n\n"
        f"📦 Название: {data['name']}\n"
        f"💰 Цена: {data['price']} ₽\n"
        f"📝 Описание: {message.text}"
    )
    await state.clear()

# Добавление категории
@dp.callback_query(F.data == "admin_add_category")
async def admin_add_category_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав")
        return
    await callback.message.edit_text("📝 Введите название новой категории:")
    await state.set_state("waiting_for_category_name")
    await callback.answer()

@dp.message(StateFilter("waiting_for_category_name"), F.text)
async def admin_add_category(message: types.Message, state: FSMContext):
    add_category(message.text)
    await message.answer(f"✅ Категория **{message.text}** добавлена в RWPlugins!")
    await state.clear()

# Удаление категории
@dp.callback_query(F.data == "admin_del_category")
async def admin_del_category_menu(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав")
        return
    
    cats = get_categories()
    if not cats:
        await callback.message.edit_text("❌ Нет категорий для удаления.", reply_markup=back_button())
        return
    
    kb = []
    for cat_id, cat_name in cats:
        kb.append([InlineKeyboardButton(text=f"🗑 {cat_name}", callback_data=f"del_cat_{cat_id}")])
    kb.append([InlineKeyboardButton(text="◀ Назад", callback_data="admin_panel")])
    
    await callback.message.edit_text("🗑 Выберите категорию для удаления:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("del_cat_"))
async def admin_del_category(callback: types.CallbackQuery):
    cat_id = int(callback.data.split("_")[2])
    delete_category(cat_id)
    await callback.message.edit_text("✅ Категория удалена!")
    await callback.answer()

# Добавление админа
@dp.callback_query(F.data == "admin_add_admin")
async def admin_add_admin_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("⛔ Только владелец RWPlugins может добавлять администраторов!")
        return
    await callback.message.edit_text("📝 Введите Telegram ID пользователя:")
    await state.set_state("waiting_for_admin_id")
    await callback.answer()

@dp.message(StateFilter("waiting_for_admin_id"), F.text)
async def admin_add_admin(message: types.Message, state: FSMContext):
    try:
        admin_id = int(message.text.strip())
        add_admin(admin_id, message.from_user.id)
        await message.answer(f"✅ Пользователь `{admin_id}` теперь администратор RWPlugins!")
    except ValueError:
        await message.answer("❌ Неверный ID! Введите число.")
    await state.clear()

# Статистика для админов
@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав")
        return
    
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    users_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM plugins")
    plugins_count = cur.fetchone()[0]
    cur.execute("SELECT SUM(downloads_count) FROM plugins")
    total_downloads = cur.fetchone()[0] or 0
    cur.execute("SELECT COUNT(*) FROM tickets WHERE status = 'open'")
    tickets_count = cur.fetchone()[0]
    conn.close()
    
    text = f"📊 **Статистика RWPlugins**\n\n"
    text += f"👥 Пользователей: {users_count}\n"
    text += f"📦 Плагинов: {plugins_count}\n"
    text += f"⬇️ Всего скачиваний: {total_downloads}\n"
    text += f"🎫 Активных тикетов: {tickets_count}"
    
    await callback.message.edit_text(text, reply_markup=back_button())

# Тикеты для админов
@dp.callback_query(F.data == "admin_tickets")
async def admin_tickets(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав")
        return
    
    tickets = get_all_tickets()
    if not tickets:
        await callback.message.edit_text("📭 Нет активных тикетов.", reply_markup=back_button())
        return
    
    text = "🎫 **Активные тикеты RWPlugins:**\n\n"
    for user_id, question, created_at in tickets:
        text += f"👤 ID: {user_id}\n"
        text += f"❓ {question[:50]}...\n"
        text += f"🕐 {created_at}\n"
        text += "━━━━━━━━━━━━━━━\n"
    
    text += "\n💡 Чтобы ответить, напишите пользователю в ЛС"
    await callback.message.edit_text(text, reply_markup=back_button())

# Рейтинг плагинов
@dp.callback_query(F.data == "admin_rating")
async def admin_rating(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав")
        return
    
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT name, downloads_count FROM plugins ORDER BY downloads_count DESC LIMIT 10")
    plugins = cur.fetchall()
    conn.close()
    
    if not plugins:
        await callback.message.edit_text("📭 Нет плагинов для рейтинга.", reply_markup=back_button())
        return
    
    text = "🏆 **Топ-10 плагинов RWPlugins:**\n\n"
    for i, (name, downloads) in enumerate(plugins, 1):
        text += f"{i}. **{name}** — {downloads} ⬇️\n"
    
    await callback.message.edit_text(text, reply_markup=back_button())

# ---------- ЗАПУСК ----------
async def main():
    print("🚀 ЗАПУСК RWPlugins БОТА...")
    print(f"🤖 Токен получен: {'✅' if BOT_TOKEN else '❌'}")
    
    init_db()
    
    # Добавляем начальные категории
    add_category("Сборки")
    add_category("PvP")
    add_category("Экономика")
    add_category("Боссы")
    
    print("✅ База данных инициализирована")
    print("✅ Категории добавлены")
    print("✅ Бот RWPlugins успешно запущен!")
    print("📊 Бот готов к работе на Render.com")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
