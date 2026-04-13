import asyncio
import os
import sqlite3
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, BotCommand, BotCommandScopeDefault
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# Настройки
logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# ВЛАДЕЛЬЦЫ - сюда добавляй ID тех, кто имеет полные права
OWNERS = [7130414548]  # Твой ID, можешь добавить ещё через запятую: [7130414548, 123456789, 987654321]

# Дата создания магазина (измени на свою)
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

class TicketQuestion(StatesGroup):
    waiting_for_question = State()

# ---------- БД ----------
def init_db():
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE)')
    cur.execute('CREATE TABLE IF NOT EXISTS plugins (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, category_id INTEGER, description TEXT, price INTEGER DEFAULT 0, file_path TEXT, downloads_count INTEGER DEFAULT 0)')
    cur.execute('CREATE TABLE IF NOT EXISTS tickets (user_id INTEGER PRIMARY KEY, question TEXT, status TEXT DEFAULT "open", created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    cur.execute('CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, added_by INTEGER, added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    cur.execute('CREATE TABLE IF NOT EXISTS owners (user_id INTEGER PRIMARY KEY, added_by INTEGER, added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    cur.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, total_downloads INTEGER DEFAULT 0)')
    cur.execute('CREATE TABLE IF NOT EXISTS downloads_stats (id INTEGER PRIMARY KEY AUTOINCREMENT, plugin_id INTEGER, user_id INTEGER, downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
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
    conn.commit()
    conn.close()

def get_plugin_stats(plugin_id):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT downloads_count FROM plugins WHERE id = ?", (plugin_id,))
    total = cur.fetchone()
    conn.close()
    return total[0] if total else 0

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

# Проверка прав
def is_owner(user_id):
    return user_id in OWNERS

def is_admin(user_id):
    if is_owner(user_id):
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

def add_owner(owner_id, added_by):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO owners (user_id, added_by) VALUES (?, ?)", (owner_id, added_by))
    conn.commit()
    conn.close()
    # Добавляем также в список OWNERS в памяти (но при перезапуске нужно будет обновить)
    if owner_id not in OWNERS:
        OWNERS.append(owner_id)

def remove_owner(owner_id):
    if owner_id in OWNERS and len(OWNERS) > 1:  # Нельзя удалить последнего владельца
        OWNERS.remove(owner_id)
        conn = sqlite3.connect('shop.db')
        cur = conn.cursor()
        cur.execute("DELETE FROM owners WHERE user_id = ?", (owner_id,))
        conn.commit()
        conn.close()
        return True
    return False

def get_owners():
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT user_id, added_by, added_at FROM owners")
    data = cur.fetchall()
    conn.close()
    return data

def get_total_downloads():
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT SUM(downloads_count) FROM plugins")
    total = cur.fetchone()[0]
    conn.close()
    return total if total else 0

def get_total_users():
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    total = cur.fetchone()[0]
    conn.close()
    return total

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
        [InlineKeyboardButton(text="👥 Управление админами", callback_data="admin_manage_admins")],
        [InlineKeyboardButton(text="👑 Управление владельцами", callback_data="admin_manage_owners")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🎫 Тикеты", callback_data="admin_tickets")],
        [InlineKeyboardButton(text="📈 Рейтинг", callback_data="admin_rating")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def back_button():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀ Назад", callback_data="main_menu")]])

# ---------- НАСТРОЙКА МЕНЮ В TELEGRAM (кнопки внизу экрана) ----------
async def set_main_menu():
    commands = [
        BotCommand(command="start", description="🏠 Главное меню"),
        BotCommand(command="menu", description="📋 Открыть меню"),
        BotCommand(command="support", description="🆘 Поддержка"),
        BotCommand(command="about", description="ℹ️ О магазине"),
        BotCommand(command="profile", description="👤 Мой профиль"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())

# ---------- ОБРАБОТЧИКИ ----------
@dp.message(Command("start"))
@dp.message(Command("menu"))
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

@dp.message(Command("support"))
async def support_cmd(message: types.Message):
    await support_menu_handler(message)

async def support_menu_handler(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✉️ Создать тикет", callback_data="create_ticket")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="main_menu")]
    ])
    await message.answer(
        "🆘 **Техническая поддержка RWPlugins**\n\n"
        "Нажмите «Создать тикет», чтобы отправить вопрос.",
        reply_markup=kb
    )

@dp.message(Command("about"))
async def about_cmd(message: types.Message):
    await about_shop_handler(message)

async def about_shop_handler(message: types.Message):
    text = "🏪 **RWPlugins - Ключ к созданию большего!**\n\n"
    text += "Мы создаём качественные плагины для Minecraft.\n"
    text += f"📅 Магазин работает с {SHOP_CREATION_DATE}\n\n"
    text += "В нашем ассортименте:\n"
    text += "• PvP системы\n"
    text += "• Экономика\n"
    text += "• Босс-арены\n"
    text += "• Кейсы и лутбоксы\n\n"
    text += "💬 По вопросам: @owner_rwplugins"
    await message.answer(text, reply_markup=back_button())

@dp.message(Command("profile"))
async def profile_cmd(message: types.Message):
    await profile_handler(message)

async def profile_handler(message: types.Message):
    user_id = message.from_user.id
    text = f"👤 **Ваш профиль RWPlugins**\n\n"
    text += f"🆔 ID: {user_id}\n"
    text += f"📅 Дата регистрации: {datetime.now().strftime('%d.%m.%Y')}\n"
    text += f"👑 Статус: {'Владелец' if is_owner(user_id) else f'Администратор' if is_admin(user_id) else 'Покупатель'}"
    await message.answer(text, reply_markup=back_button())

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
        text += f"🔹 **{name}**\n   💰 {price} ₽\n   ⬇️ {downloads}\n   📝 {desc}\n\n"
    kb = []
    for pid, name, desc, price, fpath, downloads in plugins:
        kb.append([InlineKeyboardButton(text=f"📥 {name} ({price}₽)", callback_data=f"buy_{pid}")])
    if total_pages > 1:
        nav = []
        if page > 1:
            nav.append(InlineKeyboardButton(text="◀", callback_data=f"cat_{cat_id}_{page-1}"))
        if page < total_pages:
            nav.append(InlineKeyboardButton(text="▶", callback_data=f"cat_{cat_id}_{page+1}"))
        if nav:
            kb.append(nav)
    kb.append([InlineKeyboardButton(text="◀ Назад", callback_data="categories")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "products")
async def all_products(callback: types.CallbackQuery):
    plugins, total = get_all_plugins(page=1, per_page=10)
    if not plugins:
        await callback.message.edit_text("📭 Товаров пока нет.", reply_markup=back_button())
        return
    text = "📦 **Все товары RWPlugins:**\n\n"
    for pid, name, cat_name, price, desc, downloads in plugins:
        text += f"🔹 **{name}**\n   📁 {cat_name}\n   💰 {price} ₽\n   ⬇️ {downloads}\n   📝 {desc}\n\n"
    await callback.message.edit_text(text, reply_markup=back_button())

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
        await callback.answer("❌ Плагин не найден", show_alert=True)
        return
    file_path, name, price = res
    if os.path.exists(file_path):
        increment_downloads(plugin_id, user_id)
        doc = FSInputFile(file_path)
        await callback.message.answer_document(doc, caption=f"✅ **{name}** успешно скачан!\n💰 Цена: {price} ₽")
    else:
        await callback.message.answer("❌ Файл временно недоступен. Обратитесь в поддержку.")
    await callback.answer()

@dp.callback_query(F.data == "about")
async def about_shop(callback: types.CallbackQuery):
    await about_shop_handler(callback.message)

@dp.callback_query(F.data == "profile")
async def show_profile(callback: types.CallbackQuery):
    await profile_handler(callback.message)

@dp.callback_query(F.data == "rules")
async def show_rules(callback: types.CallbackQuery):
    text = "📜 **Правила магазина RWPlugins**\n\n"
    text += "1. Запрещён возврат средств после скачивания\n"
    text += "2. Все плагины проверены\n"
    text += "3. Техподдержка отвечает в течение 24 часов\n"
    text += "4. Запрещено распространять плагины\n\n"
    text += f"📅 Магазин работает с {SHOP_CREATION_DATE}"
    await callback.message.edit_text(text, reply_markup=back_button())

@dp.callback_query(F.data == "support")
async def support_menu(callback: types.CallbackQuery):
    await support_menu_handler(callback.message)

@dp.callback_query(F.data == "create_ticket")
async def start_ticket(callback: types.CallbackQuery, state: FSMContext):
    if is_ticket_open(callback.from_user.id):
        await callback.answer("❌ У вас уже есть активный тикет!", show_alert=True)
        return
    await callback.message.edit_text("📝 Напишите ваш вопрос в одном сообщении:")
    await state.set_state(TicketQuestion.waiting_for_question)
    await callback.answer()

@dp.message(StateFilter(TicketQuestion.waiting_for_question), F.text)
async def receive_question(message: types.Message, state: FSMContext):
    create_ticket(message.from_user.id, message.text)
    await message.answer("✅ **Тикет создан!**\n\nТехподдержка ответит вам в ближайшее время.")
    await state.clear()

# ---------- АДМИН-ПАНЕЛЬ ----------
@dp.callback_query(F.data == "admin_panel")
async def admin_panel(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ У вас нет прав администратора!", show_alert=True)
        return
    await callback.message.edit_text("⚙️ **Панель администратора RWPlugins**", reply_markup=admin_panel_menu())

# Загрузка плагина
@dp.callback_query(F.data == "admin_upload")
async def admin_upload_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав", show_alert=True)
        return
    await callback.message.edit_text("📎 Отправьте файл плагина (zip, py, jar):")
    await state.set_state(UploadPlugin.waiting_for_file)
    await callback.answer()

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
            await message.answer("⚠️ Сначала создайте категорию в админ-панели")
            await state.clear()
            return
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=cat_name, callback_data=f"upload_cat_{cat_id}")] for cat_id, cat_name in cats
        ])
        await message.answer("📂 Выберите категорию:", reply_markup=kb)
        await state.set_state(UploadPlugin.waiting_for_category)
    except:
        await message.answer("❌ Введите число!")

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
    add_plugin(data['name'], data['category_id'], data['price'], message.text, data['file_path'])
    await message.answer(f"✅ **Плагин {data['name']} добавлен!**")
    await state.clear()

# Добавление категории
@dp.callback_query(F.data == "admin_add_category")
async def admin_add_category_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав", show_alert=True)
        return
    await callback.message.edit_text("📝 Введите название новой категории:")
    await state.set_state("waiting_for_category")
    await callback.answer()

@dp.message(StateFilter("waiting_for_category"), F.text)
async def admin_add_category(message: types.Message, state: FSMContext):
    add_category(message.text)
    await message.answer(f"✅ Категория **{message.text}** добавлена!")
    await state.clear()

# Удаление категории
@dp.callback_query(F.data == "admin_del_category")
async def admin_del_category_menu(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав", show_alert=True)
        return
    cats = get_categories()
    if not cats:
        await callback.message.edit_text("❌ Нет категорий для удаления.", reply_markup=back_button())
        return
    kb = [[InlineKeyboardButton(text=f"🗑 {cat_name}", callback_data=f"del_cat_{cat_id}")] for cat_id, cat_name in cats]
    kb.append([InlineKeyboardButton(text="◀ Назад", callback_data="admin_panel")])
    await callback.message.edit_text("🗑 Выберите категорию для удаления:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("del_cat_"))
async def admin_del_category(callback: types.CallbackQuery):
    cat_id = int(callback.data.split("_")[2])
    delete_category(cat_id)
    await callback.message.edit_text("✅ Категория удалена!")
    await callback.answer()

# Управление админами
@dp.callback_query(F.data == "admin_manage_admins")
async def admin_manage_admins(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав", show_alert=True)
        return
    
    kb = [
        [InlineKeyboardButton(text="➕ Добавить админа", callback_data="admin_add_admin")],
        [InlineKeyboardButton(text="🗑 Удалить админа", callback_data="admin_remove_admin")],
        [InlineKeyboardButton(text="📋 Список админов", callback_data="admin_list_admins")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="admin_panel")]
    ]
    await callback.message.edit_text("👥 **Управление администраторами**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "admin_add_admin")
async def admin_add_admin_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_owner(callback.from_user.id):
        await callback.answer("⛔ Только владельцы могут добавлять админов!", show_alert=True)
        return
    await callback.message.edit_text("📝 Введите Telegram ID пользователя:")
    await state.set_state("waiting_for_admin_id")
    await callback.answer()

@dp.message(StateFilter("waiting_for_admin_id"), F.text)
async def admin_add_admin(message: types.Message, state: FSMContext):
    try:
        admin_id = int(message.text)
        add_admin(admin_id, message.from_user.id)
        await message.answer(f"✅ Пользователь `{admin_id}` теперь администратор!")
    except:
        await message.answer("❌ Неверный ID!")
    await state.clear()

@dp.callback_query(F.data == "admin_remove_admin")
async def admin_remove_admin_menu(callback: types.CallbackQuery):
    if not is_owner(callback.from_user.id):
        await callback.answer("⛔ Только владельцы могут удалять админов!", show_alert=True)
        return
    admins = get_admins()
    if not admins:
        await callback.message.edit_text("❌ Нет администраторов для удаления.", reply_markup=back_button())
        return
    kb = [[InlineKeyboardButton(text=f"🗑 ID: {admin_id}", callback_data=f"remove_admin_{admin_id}")] for admin_id, _, _ in admins]
    kb.append([InlineKeyboardButton(text="◀ Назад", callback_data="admin_manage_admins")])
    await callback.message.edit_text("🗑 Выберите администратора для удаления:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("remove_admin_"))
async def admin_remove_admin(callback: types.CallbackQuery):
    admin_id = int(callback.data.split("_")[2])
    remove_admin(admin_id)
    await callback.message.edit_text(f"✅ Администратор {admin_id} удалён!")
    await callback.answer()

@dp.callback_query(F.data == "admin_list_admins")
async def admin_list_admins(callback: types.CallbackQuery):
    admins = get_admins()
    owners_list = OWNERS
    
    text = "👑 **Владельцы:**\n"
    for owner_id in owners_list:
        text += f"• `{owner_id}`\n"
    
    text += "\n👥 **Администраторы:**\n"
    if admins:
        for admin_id, added_by, added_at in admins:
            text += f"• `{admin_id}` (добавлен {added_at[:10]})\n"
    else:
        text += "Нет администраторов\n"
    
    await callback.message.edit_text(text, reply_markup=back_button())

# Управление владельцами
@dp.callback_query(F.data == "admin_manage_owners")
async def admin_manage_owners(callback: types.CallbackQuery):
    if not is_owner(callback.from_user.id):
        await callback.answer("⛔ Только владельцы могут управлять владельцами!", show_alert=True)
        return
    
    kb = [
        [InlineKeyboardButton(text="➕ Добавить владельца", callback_data="admin_add_owner")],
        [InlineKeyboardButton(text="🗑 Удалить владельца", callback_data="admin_remove_owner")],
        [InlineKeyboardButton(text="📋 Список владельцев", callback_data="admin_list_owners")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="admin_panel")]
    ]
    await callback.message.edit_text("👑 **Управление владельцами**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "admin_add_owner")
async def admin_add_owner_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_owner(callback.from_user.id):
        await callback.answer("⛔ Нет прав!", show_alert=True)
        return
    await callback.message.edit_text("📝 Введите Telegram ID нового владельца:")
    await state.set_state("waiting_for_owner_id")
    await callback.answer()

@dp.message(StateFilter("waiting_for_owner_id"), F.text)
async def admin_add_owner(message: types.Message, state: FSMContext):
    try:
        owner_id = int(message.text)
        add_owner(owner_id, message.from_user.id)
        await message.answer(f"✅ Пользователь `{owner_id}` теперь владелец!")
    except:
        await message.answer("❌ Неверный ID!")
    await state.clear()

@dp.callback_query(F.data == "admin_remove_owner")
async def admin_remove_owner_menu(callback: types.CallbackQuery):
    if not is_owner(callback.from_user.id):
        await callback.answer("⛔ Нет прав!", show_alert=True)
        return
    
    if len(OWNERS) <= 1:
        await callback.message.edit_text("❌ Нельзя удалить единственного владельца!", reply_markup=back_button())
        return
    
    kb = [[InlineKeyboardButton(text=f"🗑 ID: {owner_id}", callback_data=f"remove_owner_{owner_id}")] for owner_id in OWNERS if owner_id != callback.from_user.id]
    kb.append([InlineKeyboardButton(text="◀ Назад", callback_data="admin_manage_owners")])
    await callback.message.edit_text("🗑 Выберите владельца для удаления:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("remove_owner_"))
async def admin_remove_owner(callback: types.CallbackQuery):
    owner_id = int(callback.data.split("_")[2])
    if remove_owner(owner_id):
        await callback.message.edit_text(f"✅ Владелец {owner_id} удалён!")
    else:
        await callback.message.edit_text("❌ Нельзя удалить единственного владельца!")
    await callback.answer()

@dp.callback_query(F.data == "admin_list_owners")
async def admin_list_owners(callback: types.CallbackQuery):
    text = "👑 **Список владельцев:**\n\n"
    for owner_id in OWNERS:
        text += f"• `{owner_id}`\n"
    await callback.message.edit_text(text, reply_markup=back_button())

# Статистика
@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав", show_alert=True)
        return
    
    users = get_total_users()
    plugins_count = len(get_all_plugins()[0])
    total_downloads = get_total_downloads()
    tickets = len(get_all_tickets())
    categories = len(get_categories())
    
    text = f"📊 **Статистика RWPlugins**\n\n"
    text += f"👥 Пользователей: {users}\n"
    text += f"📦 Плагинов: {plugins_count}\n"
    text += f"📁 Категорий: {categories}\n"
    text += f"⬇️ Всего скачиваний: {total_downloads}\n"
    text += f"🎫 Активных тикетов: {tickets}\n"
    text += f"👑 Владельцев: {len(OWNERS)}\n"
    text += f"👥 Администраторов: {len(get_admins())}\n"
    text += f"📅 Магазин работает с {SHOP_CREATION_DATE}"
    
    await callback.message.edit_text(text, reply_markup=back_button())

@dp.callback_query(F.data == "admin_tickets")
async def admin_tickets(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав", show_alert=True)
        return
    tickets = get_all_tickets()
    if not tickets:
        await callback.message.edit_text("📭 Нет активных тикетов.", reply_markup=back_button())
        return
    text = "🎫 **Активные тикеты:**\n\n"
    for user_id, question, created_at in tickets:
        text += f"👤 ID: {user_id}\n❓ {question[:50]}...\n🕐 {created_at}\n━━━━━━━━━━\n"
    text += "\n💡 Ответьте пользователю в ЛС"
    await callback.message.edit_text(text, reply_markup=back_button())

@dp.callback_query(F.data == "admin_rating")
async def admin_rating(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав", show_alert=True)
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
    init_db()
    
    # Добавляем начальные категории
    add_category("Сборки")
    add_category("PvP")
    add_category("Экономика")
    add_category("Боссы")
    
    # Настраиваем меню в Telegram
    await set_main_menu()
    
    print(f"✅ Бот RWPlugins успешно запущен!")
    print(f"👑 Владельцы: {OWNERS}")
    print(f"📅 Дата создания магазина: {SHOP_CREATION_DATE}")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
