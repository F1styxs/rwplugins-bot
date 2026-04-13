import asyncio
import os
import sqlite3
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ВКЛЮЧАЕМ ЛОГИРОВАНИЕ
logging.basicConfig(level=logging.INFO)

# ВСТАВЬ СВОИ ДАННЫЕ
BOT_TOKEN = "8699215386:AAE-tBx_KDBIck8w2VrE4vTvXdZbRhy-0QA"
OWNER_ID = 7130414548  # Твой ID (владелец)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ---------- СОСТОЯНИЯ ----------
class UploadPlugin(StatesGroup):
    waiting_for_file = State()
    waiting_for_name = State()
    waiting_for_category = State()
    waiting_for_description = State()

class AdminReply(StatesGroup):
    waiting_for_reply = State()

class AddAdmin(StatesGroup):
    waiting_for_user_id = State()

# ---------- ИНИЦИАЛИЗАЦИЯ БД ----------
def init_db():
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    
    # Категории
    cur.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE
        )
    ''')
    
    # Плагины с полем downloads_count
    cur.execute('''
        CREATE TABLE IF NOT EXISTS plugins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            category_id INTEGER,
            description TEXT,
            file_path TEXT,
            downloads_count INTEGER DEFAULT 0,
            FOREIGN KEY(category_id) REFERENCES categories(id)
        )
    ''')
    
    # Тикеты
    cur.execute('''
        CREATE TABLE IF NOT EXISTS tickets (
            user_id INTEGER PRIMARY KEY,
            status TEXT DEFAULT 'open',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Админы (кроме владельца)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            added_by INTEGER,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Статистика скачиваний по дням
    cur.execute('''
        CREATE TABLE IF NOT EXISTS downloads_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plugin_id INTEGER,
            user_id INTEGER,
            downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(plugin_id) REFERENCES plugins(id)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")

# ---------- ФУНКЦИИ ДЛЯ АДМИНОВ ----------
def is_admin(user_id):
    """Проверяет, является ли пользователь админом или владельцем"""
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

# ---------- ФУНКЦИИ ДЛЯ КАТЕГОРИЙ И ПЛАГИНОВ ----------
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
    cur.execute('''
        INSERT INTO plugins (name, category_id, description, file_path, downloads_count)
        VALUES (?, ?, ?, ?, 0)
    ''', (name, category_id, description, file_path))
    conn.commit()
    conn.close()

def get_plugins_by_category(category_id):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT id, name, description, file_path, downloads_count FROM plugins WHERE category_id = ?", (category_id,))
    data = cur.fetchall()
    conn.close()
    return data

def get_all_plugins():
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT p.id, p.name, c.name, p.description, p.downloads_count FROM plugins p JOIN categories c ON p.category_id = c.id")
    data = cur.fetchall()
    conn.close()
    return data

def increment_downloads(plugin_id, user_id):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    # Увеличиваем счётчик
    cur.execute("UPDATE plugins SET downloads_count = downloads_count + 1 WHERE id = ?", (plugin_id,))
    # Добавляем запись в статистику
    cur.execute("INSERT INTO downloads_stats (plugin_id, user_id) VALUES (?, ?)", (plugin_id, user_id))
    conn.commit()
    conn.close()

def get_plugin_stats(plugin_id):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    # Общее количество скачиваний
    cur.execute("SELECT downloads_count FROM plugins WHERE id = ?", (plugin_id,))
    total = cur.fetchone()[0]
    # За последние 7 дней
    week_ago = datetime.now() - timedelta(days=7)
    cur.execute("SELECT COUNT(*) FROM downloads_stats WHERE plugin_id = ? AND downloaded_at > ?", (plugin_id, week_ago))
    week = cur.fetchone()[0]
    conn.close()
    return total, week

def get_all_stats():
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    # Всего скачиваний всех плагинов
    cur.execute("SELECT SUM(downloads_count) FROM plugins")
    total_all = cur.fetchone()[0] or 0
    # За последние 7 дней
    week_ago = datetime.now() - timedelta(days=7)
    cur.execute("SELECT COUNT(*) FROM downloads_stats WHERE downloaded_at > ?", (week_ago,))
    week_all = cur.fetchone()[0]
    # Количество плагинов
    cur.execute("SELECT COUNT(*) FROM plugins")
    plugins_count = cur.fetchone()[0]
    # Количество категорий
    cur.execute("SELECT COUNT(*) FROM categories")
    categories_count = cur.fetchone()[0]
    conn.close()
    return total_all, week_all, plugins_count, categories_count

# ---------- ФУНКЦИИ ДЛЯ ТИКЕТОВ ----------
def create_ticket(user_id):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("REPLACE INTO tickets (user_id, status) VALUES (?, 'open')", (user_id,))
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
    cur.execute("SELECT user_id, created_at FROM tickets WHERE status = 'open'")
    data = cur.fetchall()
    conn.close()
    return data

# ---------- КЛАВИАТУРЫ ----------
def main_menu(is_admin_user=False):
    kb = [
        [InlineKeyboardButton(text="📂 Категории", callback_data="categories")],
        [InlineKeyboardButton(text="🛍 О магазине", callback_data="about")],
        [InlineKeyboardButton(text="📋 Список товаров", callback_data="products")],
        [InlineKeyboardButton(text="🆘 Поддержка", callback_data="support")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")]
    ]
    if is_admin_user:
        kb.append([InlineKeyboardButton(text="⚙️ Админ-панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def admin_panel_menu():
    kb = [
        [InlineKeyboardButton(text="📥 Загрузить плагин", callback_data="admin_upload")],
        [InlineKeyboardButton(text="➕ Добавить категорию", callback_data="admin_add_category")],
        [InlineKeyboardButton(text="🗑 Удалить категорию", callback_data="admin_del_category")],
        [InlineKeyboardButton(text="👥 Добавить админа", callback_data="admin_add_admin")],
        [InlineKeyboardButton(text="📊 Статистика магазина", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🎫 Активные тикеты", callback_data="admin_tickets")],
        [InlineKeyboardButton(text="📈 Рейтинг плагинов", callback_data="admin_rating")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def back_button():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀ Назад", callback_data="main_menu")]
    ])

# ---------- ОБРАБОТЧИКИ ----------
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    is_admin_user = is_admin(user_id)
    await message.answer(
        "👋 Привет! Я бот с плагинами и поддержкой.\n\n"
        "📌 Навигация по кнопкам ниже:",
        reply_markup=main_menu(is_admin_user)
    )

@dp.callback_query(F.data == "main_menu")
async def back_to_main(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    is_admin_user = is_admin(user_id)
    await callback.message.edit_text(
        "🏠 Главное меню:",
        reply_markup=main_menu(is_admin_user)
    )

@dp.callback_query(F.data == "stats")
async def show_stats(callback: types.CallbackQuery):
    total_all, week_all, plugins_count, categories_count = get_all_stats()
    text = f"📊 **Общая статистика магазина**\n\n"
    text += f"📦 Всего плагинов: {plugins_count}\n"
    text += f"📁 Всего категорий: {categories_count}\n"
    text += f"⬇️ Всего скачиваний: {total_all}\n"
    text += f"📈 Скачиваний за 7 дней: {week_all}\n"
    await callback.message.edit_text(text, reply_markup=back_button())

@dp.callback_query(F.data == "categories")
async def show_categories(callback: types.CallbackQuery):
    cats = get_categories()
    if not cats:
        await callback.message.edit_text("❌ Категорий пока нет.", reply_markup=back_button())
        return
    kb = []
    for cat_id, cat_name in cats:
        kb.append([InlineKeyboardButton(text=cat_name, callback_data=f"cat_{cat_id}")])
    kb.append([InlineKeyboardButton(text="◀ Назад", callback_data="main_menu")])
    await callback.message.edit_text("📁 Выберите категорию:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("cat_"))
async def show_plugins(callback: types.CallbackQuery):
    cat_id = int(callback.data.split("_")[1])
    plugins = get_plugins_by_category(cat_id)
    if not plugins:
        await callback.message.edit_text("❌ В этой категории пока нет плагинов.", reply_markup=back_button())
        return
    kb = []
    for pid, name, desc, fpath, downloads in plugins:
        kb.append([InlineKeyboardButton(text=f"📥 {name} (⬇️ {downloads})", callback_data=f"download_{pid}")])
    kb.append([InlineKeyboardButton(text="◀ Назад", callback_data="categories")])
    await callback.message.edit_text("🔧 Доступные плагины:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("download_"))
async def download_plugin(callback: types.CallbackQuery):
    plugin_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT file_path, name FROM plugins WHERE id = ?", (plugin_id,))
    res = cur.fetchone()
    conn.close()
    
    if not res:
        await callback.answer("❌ Файл не найден")
        return
    
    file_path, name = res
    if os.path.exists(file_path):
        # Увеличиваем счётчик скачиваний
        increment_downloads(plugin_id, user_id)
        doc = FSInputFile(file_path)
        await callback.message.answer_document(doc, caption=f"✅ {name} успешно скачан!\n⬇️ Скачиваний: {get_plugin_stats(plugin_id)[0]}")
    else:
        await callback.message.answer("❌ Файл удалён с сервера.")
    await callback.answer()

@dp.callback_query(F.data == "about")
async def about_shop(callback: types.CallbackQuery):
    text = "🧩 **О магазине**\n\nМы продаём качественные плагины и сборки. Все файлы проверены.\nПо вопросам — пишите в поддержку."
    await callback.message.edit_text(text, reply_markup=back_button())

@dp.callback_query(F.data == "products")
async def all_products(callback: types.CallbackQuery):
    items = get_all_plugins()
    if not items:
        await callback.message.edit_text("📭 Товаров пока нет.", reply_markup=back_button())
        return
    text = "📦 **Наши товары:**\n\n"
    for pid, name, cat_name, desc, downloads in items:
        text += f"🔹 **{name}**\n   📁 {cat_name}\n   📝 {desc}\n   ⬇️ Скачиваний: {downloads}\n\n"
    await callback.message.edit_text(text, reply_markup=back_button())

# ---------- ПОДДЕРЖКА (ТИКЕТЫ) ----------
@dp.callback_query(F.data == "support")
async def support_menu(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✉️ Создать тикет", callback_data="create_ticket")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="main_menu")]
    ])
    await callback.message.edit_text("🆘 **Поддержка**\nВыберите действие:", reply_markup=kb)

@dp.callback_query(F.data == "create_ticket")
async def create_ticket_handler(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if is_ticket_open(user_id):
        await callback.answer("У вас уже есть активный тикет! Дождитесь ответа.")
        return
    create_ticket(user_id)
    await callback.message.edit_text("📝 Напишите вашу проблему одним сообщением.\n(Администратор ответит вам сюда)")
    await state.set_state("waiting_for_ticket_text")

@dp.message(StateFilter("waiting_for_ticket_text"))
async def receive_ticket_text(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if not is_ticket_open(user_id):
        await message.answer("❌ Тикет не найден. Начните заново /start")
        await state.clear()
        return
    
    ticket_text = message.text
    # Отправляем всем админам и владельцу
    admin_list = [OWNER_ID] + [admin[0] for admin in get_admins()]
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Ответить", callback_data=f"reply_to_{user_id}")],
        [InlineKeyboardButton(text="🔒 Закрыть тикет", callback_data=f"close_ticket_{user_id}")]
    ])
    
    for admin_id in admin_list:
        try:
            await bot.send_message(
                admin_id,
                f"🆕 **Новый тикет от** {message.from_user.full_name} (ID: {user_id})\n\n📩 Сообщение:\n{ticket_text}",
                reply_markup=kb
            )
        except:
            pass
    
    await message.answer("✅ Ваше сообщение отправлено администраторам. Ожидайте ответа.")
    await state.clear()

# ---------- АДМИН-ПАНЕЛЬ ----------
@dp.callback_query(F.data == "admin_panel")
async def admin_panel(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ У вас нет прав администратора!")
        return
    await callback.message.edit_text("⚙️ **Админ-панель**\nВыберите действие:", reply_markup=admin_panel_menu())

# Загрузка плагина
@dp.callback_query(F.data == "admin_upload")
async def admin_upload_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав")
        return
    await callback.message.edit_text("📎 Отправьте файл плагина (zip/py/любой)")
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
    cats = get_categories()
    if not cats:
        await message.answer("⚠️ Сначала создайте категорию командой /add_category Название")
        await state.clear()
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=cat_name, callback_data=f"upload_cat_{cat_id}")] for cat_id, cat_name in cats
    ])
    await message.answer("📂 Выберите категорию:", reply_markup=kb)
    await state.set_state(UploadPlugin.waiting_for_category)

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
        description=message.text,
        file_path=data['file_path']
    )
    await message.answer("✅ Плагин успешно добавлен в базу и доступен для скачивания!")
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
    await message.answer(f"✅ Категория '{message.text}' добавлена!")
    await state.clear()

# Удаление категории
@dp.callback_query(F.data == "admin_del_category")
async def admin_del_category_menu(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав")
        return
    cats = get_categories()
    if not cats:
        await callback.message.edit_text("❌ Нет категорий для удаления.")
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
        await callback.answer("⛔ Только владелец может добавлять админов!")
        return
    await callback.message.edit_text("📝 Введите Telegram ID пользователя, которого хотите сделать админом:")
    await state.set_state(AddAdmin.waiting_for_user_id)
    await callback.answer()

@dp.message(StateFilter(AddAdmin.waiting_for_user_id), F.text)
async def admin_add_admin(message: types.Message, state: FSMContext):
    try:
        admin_id = int(message.text)
        add_admin(admin_id, message.from_user.id)
        await message.answer(f"✅ Пользователь {admin_id} теперь администратор!")
    except:
        await message.answer("❌ Неверный ID. Введите число.")
    await state.clear()

# Статистика для админов
@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав")
        return
    total_all, week_all, plugins_count, categories_count = get_all_stats()
    text = f"📊 **Детальная статистика магазина**\n\n"
    text += f"📦 Всего плагинов: {plugins_count}\n"
    text += f"📁 Всего категорий: {categories_count}\n"
    text += f"⬇️ Всего скачиваний: {total_all}\n"
    text += f"📈 Скачиваний за 7 дней: {week_all}\n\n"
    
    # Топ-5 плагинов
    plugins = get_all_plugins()
    plugins_sorted = sorted(plugins, key=lambda x: x[4], reverse=True)[:5]
    if plugins_sorted:
        text += "🏆 **Топ-5 плагинов:**\n"
        for i, (_, name, cat, _, downloads) in enumerate(plugins_sorted, 1):
            text += f"{i}. {name} - {downloads} ⬇️\n"
    
    await callback.message.edit_text(text, reply_markup=back_button())

# Рейтинг плагинов
@dp.callback_query(F.data == "admin_rating")
async def admin_rating(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав")
        return
    plugins = get_all_plugins()
    plugins_sorted = sorted(plugins, key=lambda x: x[4], reverse=True)
    
    if not plugins_sorted:
        await callback.message.edit_text("❌ Нет плагинов для отображения.")
        return
    
    text = "📊 **Рейтинг плагинов по скачиваниям:**\n\n"
    for i, (_, name, cat, _, downloads) in enumerate(plugins_sorted, 1):
        text += f"{i}. **{name}**\n   📁 {cat}\n   ⬇️ {downloads} скачиваний\n\n"
    
    await callback.message.edit_text(text, reply_markup=back_button())

# Активные тикеты
@dp.callback_query(F.data == "admin_tickets")
async def admin_tickets(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав")
        return
    tickets = get_all_tickets()
    if not tickets:
        await callback.message.edit_text("📭 Нет активных тикетов.")
        return
    
    text = "🎫 **Активные тикеты:**\n\n"
    for user_id, created_at in tickets:
        text += f"👤 ID: {user_id}\n   🕐 Создан: {created_at}\n   ━━━━━━━━━━━━━━━\n"
    
    await callback.message.edit_text(text, reply_markup=back_button())

# Ответ на тикет
@dp.callback_query(F.data.startswith("reply_to_"))
async def admin_reply_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Только для админов")
        return
    user_id = int(callback.data.split("_")[2])
    await state.update_data(reply_user_id=user_id)
    await callback.message.answer("✏️ Введите ваш ответ для пользователя:")
    await state.set_state(AdminReply.waiting_for_reply)
    await callback.answer()

@dp.message(StateFilter(AdminReply.waiting_for_reply))
async def admin_send_reply(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("reply_user_id")
    if not user_id:
        await message.answer("Ошибка")
        await state.clear()
        return
    reply_text = message.text
    try:
        await bot.send_message(user_id, f"📨 **Ответ поддержки:**\n{reply_text}")
        await message.answer("✅ Ответ отправлен пользователю.")
    except:
        await message.answer("❌ Не удалось отправить (пользователь заблокировал бота?)")
    await state.clear()

@dp.callback_query(F.data.startswith("close_ticket_"))
async def close_ticket_admin(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Только для админов")
        return
    user_id = int(callback.data.split("_")[2])
    close_ticket(user_id)
    await callback.message.edit_text("✅ Тикет закрыт.")
    try:
        await bot.send_message(user_id, "🔒 Ваш тикет закрыт администратором. Спасибо за обращение!")
    except:
        pass

# ---------- ЗАПУСК ----------
async def main():
    print("🚀 ЗАПУСК БОТА...")
    init_db()
    # Добавляем начальные категории
    add_category("Сборки")
    add_category("Плагины")
    print("✅ Бот запущен! Нажми Ctrl+C для остановки")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())