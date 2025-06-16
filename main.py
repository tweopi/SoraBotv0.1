import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, FSInputFile, ReplyKeyboardRemove
import sqlite3
import asyncio
import os
from pathlib import Path
import pandas as pd
from datetime import datetime
from io import BytesIO
from openpyxl import Workbook
from aiogram.types import BufferedInputFile
import os
from dotenv import load_dotenv

# Загрузка токена из переменных окружения
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(token="8143304952:AAHm-ha-Cb2vqOHeOyWGO1B4sdS6wbzBiBQ")
dp = Dispatcher()

# Состояния пользователей
user_states = {}
user_data = {}

# ===== НАСТРОЙКА БАЗЫ ДАННЫХ =====
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "SoraClub.db"  # Теперь в корне проекта
EXPORT_DIR = BASE_DIR / "exports"  # Папка для экспортов

# Создаем необходимые директории
EXPORT_DIR.mkdir(exist_ok=True)

# Подключение к SQLite
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

# Создаем таблицу товаров (если не существует)
cursor.execute('''
               CREATE TABLE IF NOT EXISTS products
               (
                   id
                   INTEGER
                   PRIMARY
                   KEY
                   AUTOINCREMENT,
                   name
                   TEXT
                   NOT
                   NULL,
                   quantity
                   INTEGER
                   DEFAULT
                   1,
                   category
                   TEXT,
                   added_date
                   TIMESTAMP
                   DEFAULT
                   CURRENT_TIMESTAMP
               )
               ''')

# Создаем таблицу пользователей
cursor.execute('''
               CREATE TABLE IF NOT EXISTS users
               (
                   user_id
                   INTEGER
                   PRIMARY
                   KEY,
                   username
                   TEXT,
                   first_name
                   TEXT,
                   is_admin
                   BOOLEAN
                   DEFAULT
                   0,
                   is_banned
                   BOOLEAN
                   DEFAULT
                   0,
                   added_date
                   TIMESTAMP
                   DEFAULT
                   CURRENT_TIMESTAMP
               )
               ''')

# Создаем таблицу для логов действий
cursor.execute('''
               CREATE TABLE IF NOT EXISTS action_logs
               (
                   id
                   INTEGER
                   PRIMARY
                   KEY
                   AUTOINCREMENT,
                   user_id
                   INTEGER,
                   action
                   TEXT,
                   details
                   TEXT,
                   timestamp
                   TIMESTAMP
                   DEFAULT
                   CURRENT_TIMESTAMP
               )
               ''')

conn.commit()

# ID главного администратора (замените на ваш Telegram ID)
# Чтобы узнать свой ID, напишите @userinfobot в Telegram
MAIN_ADMIN_ID = 7873867301  # Замените на ваш реальный Telegram ID

# Функция для регистрации пользователя
def register_user(user_id, username, first_name):
    try:
        cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        if not cursor.fetchone():
            is_admin = 1 if user_id == MAIN_ADMIN_ID else 0
            cursor.execute(
                "INSERT INTO users (user_id, username, first_name, is_admin) VALUES (?, ?, ?, ?)",
                (user_id, username, first_name, is_admin)
            )
            conn.commit()
            return True
        return False
    except Exception as e:
        logger.error(f"Ошибка при регистрации пользователя: {e}")
        return False

# Функция для проверки прав администратора
def is_admin(user_id):
    try:
        cursor.execute("SELECT is_admin FROM users WHERE user_id = ? AND is_banned = 0", (user_id,))
        result = cursor.fetchone()
        return result and result[0] == 1
    except:
        return False

# Функция для проверки бана пользователя
def is_banned(user_id):
    try:
        cursor.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        return result and result[0] == 1
    except:
        return False

# Функция для логирования действий
async def log_action(user_id, action, details=""):
    try:
        cursor.execute(
            "INSERT INTO action_logs (user_id, action, details) VALUES (?, ?, ?)",
            (user_id, action, details)
        )
        conn.commit()

        # Отправляем уведомление главному администратору
        if user_id != MAIN_ADMIN_ID:
            cursor.execute("SELECT username, first_name FROM users WHERE user_id = ?", (user_id,))
            user_info = cursor.fetchone()
            username = user_info[0] if user_info and user_info[0] else "без username"
            first_name = user_info[1] if user_info and user_info[1] else "Неизвестно"

            notification = (
                f"🔔 Действие пользователя:\n"
                f"👤 {first_name} (@{username})\n"
                f"🆔 ID: {user_id}\n"
                f"⚡ Действие: {action}\n"
                f"📝 Детали: {details}\n"
                f"🕐 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )

            try:
                await bot.send_message(MAIN_ADMIN_ID, notification)
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления админу: {e}")
    except Exception as e:
        logger.error(f"Ошибка логирования действия: {e}")


# ===== КЛАВИАТУРЫ =====
def get_main_keyboard(user_id):
    keyboard = [
        [KeyboardButton(text="📦 Добавить товар")],
        [KeyboardButton(text="📊 Посмотреть склад"), KeyboardButton(text="🔍 Поиск товара")],
        [KeyboardButton(text="✏️ Редактировать"), KeyboardButton(text="❌ Удалить товар")],
        [KeyboardButton(text="📥 Экспорт в Excel"), KeyboardButton(text="🚨 Проверить остатки")]
    ]

    # Добавляем админ-панель для администраторов
    if is_admin(user_id):
        keyboard.append([KeyboardButton(text="👑 Админ-панель")])

    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_admin_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👥 Управление пользователями")],
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="📋 Логи действий")],
            [KeyboardButton(text="🔙 Назад в главное меню")]
        ],
        resize_keyboard=True
    )

def get_user_management_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👀 Список пользователей")],
            [KeyboardButton(text="⚡ Назначить админа"), KeyboardButton(text="🚫 Заблокировать")],
            [KeyboardButton(text="✅ Разблокировать"), KeyboardButton(text="❌ Снять админа")],
            [KeyboardButton(text="🔙 Назад в админ-панель")]
        ],
        resize_keyboard=True
    )


# ===== КОМАНДА /start =====
@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name

    # Проверяем, заблокирован ли пользователь
    if is_banned(user_id):
        await message.answer("❌ Ваш доступ к боту заблокирован администратором.")
        return

    # Регистрируем пользователя
    is_new_user = register_user(user_id, username, first_name)

    user_states[user_id] = None
    user_data[user_id] = {}

    welcome_text = "🛒 Добро пожаловать в складской бот!\n"
    if is_new_user:
        welcome_text += "✅ Вы успешно зарегистрированы!\n"
        await log_action(user_id, "Новый пользователь", f"Первый запуск бота")

    welcome_text += "Выберите действие из меню ниже:"

    await message.answer(welcome_text, reply_markup=get_main_keyboard(user_id))


# ===== MIDDLEWARE ДЛЯ ПРОВЕРКИ ДОСТУПА =====
def access_required(func):
    async def wrapper(message: types.Message):
        user_id = message.from_user.id
        if is_banned(user_id):
            await message.answer("❌ Ваш доступ к боту заблокирован.")
            return
        return await func(message)
    return wrapper

def admin_required(func):
    async def wrapper(message: types.Message):
        user_id = message.from_user.id
        if is_banned(user_id):
            await message.answer("❌ Ваш доступ к боту заблокирован.")
            return
        if not is_admin(user_id):
            await message.answer("❌ У вас нет прав администратора для выполнения этого действия.")
            return
        return await func(message)
    return wrapper

# ===== АДМИН-ПАНЕЛЬ =====
@dp.message(F.text == "👑 Админ-панель")
@admin_required
async def admin_panel(message: types.Message):
    await message.answer(
        "👑 Панель администратора\n"
        "Выберите действие:",
        reply_markup=get_admin_keyboard()
    )

@dp.message(F.text == "👥 Управление пользователями")
@admin_required
async def user_management(message: types.Message):
    await message.answer(
        "👥 Управление пользователями\n"
        "Выберите действие:",
        reply_markup=get_user_management_keyboard()
    )

@dp.message(F.text == "👀 Список пользователей")
@admin_required
async def list_users(message: types.Message):
    try:
        cursor.execute("SELECT user_id, username, first_name, is_admin, is_banned, added_date FROM users ORDER BY added_date DESC")
        users = cursor.fetchall()

        if not users:
            await message.answer("👥 Пользователей нет в базе данных.")
            return

        response = "👥 Список пользователей:\n\n"
        for user in users:
            status = ""
            if user[3]:  # is_admin
                status += "👑"
            if user[4]:  # is_banned
                status += "🚫"
            if not status:
                status = "👤"

            response += (
                f"{status} {user[2] or 'Без имени'}\n"
                f"@{user[1] or 'без username'}\n"
                f"ID: {user[0]}\n"
                f"Дата регистрации: {user[5]}\n\n"
            )

        if len(response) > 4000:
            for i in range(0, len(response), 4000):
                await message.answer(response[i:i+4000])
        else:
            await message.answer(response)

    except Exception as e:
        logger.error(f"Ошибка при получении списка пользователей: {e}")
        await message.answer("❌ Ошибка при получении списка пользователей.")

@dp.message(F.text == "📊 Статистика")
@admin_required
async def admin_stats(message: types.Message):
    try:
        # Статистика пользователей
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1")
        admin_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
        banned_count = cursor.fetchone()[0]

        # Статистика товаров
        cursor.execute("SELECT COUNT(*) FROM products")
        total_products = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM products WHERE quantity < 10")
        low_stock = cursor.fetchone()[0]

        # Статистика действий за последние 24 часа
        cursor.execute("SELECT COUNT(*) FROM action_logs WHERE timestamp > datetime('now', '-1 day')")
        actions_24h = cursor.fetchone()[0]

        response = (
            f"📊 Статистика бота:\n\n"
            f"👥 Пользователи:\n"
            f"├ Всего: {total_users}\n"
            f"├ Администраторы: {admin_count}\n"
            f"└ Заблокированы: {banned_count}\n\n"
            f"📦 Товары:\n"
            f"├ Всего: {total_products}\n"
            f"└ С низким запасом: {low_stock}\n\n"
            f"⚡ Активность:\n"
            f"└ Действий за 24ч: {actions_24h}"
        )

        await message.answer(response)

    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {e}")
        await message.answer("❌ Ошибка при получении статистики.")

@dp.message(F.text == "📋 Логи действий")
@admin_required
async def view_logs(message: types.Message):
    try:
        cursor.execute("""
            SELECT al.action, al.details, al.timestamp, u.first_name, u.username 
            FROM action_logs al 
            LEFT JOIN users u ON al.user_id = u.user_id 
            ORDER BY al.timestamp DESC LIMIT 20
        """)
        logs = cursor.fetchall()

        if not logs:
            await message.answer("📋 Логи действий пусты.")
            return

        response = "📋 Последние 20 действий:\n\n"
        for log in logs:
            username = f"@{log[4]}" if log[4] else "без username"
            first_name = log[3] or "Неизвестно"
            response += (
                f"⚡ {log[0]}\n"
                f"👤 {first_name} ({username})\n"
                f"📝 {log[1]}\n"
                f"🕐 {log[2]}\n\n"
            )

        if len(response) > 4000:
            for i in range(0, len(response), 4000):
                await message.answer(response[i:i+4000])
        else:
            await message.answer(response)

    except Exception as e:
        logger.error(f"Ошибка при получении логов: {e}")
        await message.answer("❌ Ошибка при получении логов.")

# Обработчики для управления пользователями
@dp.message(F.text == "⚡ Назначить админа")
@admin_required
async def promote_user_start(message: types.Message):
    user_states[message.from_user.id] = "promoting_user"
    await message.answer("Введите ID пользователя для назначения администратором:", reply_markup=ReplyKeyboardRemove())

@dp.message(F.text == "🚫 Заблокировать")
@admin_required
async def ban_user_start(message: types.Message):
    user_states[message.from_user.id] = "banning_user"
    await message.answer("Введите ID пользователя для блокировки:", reply_markup=ReplyKeyboardRemove())

@dp.message(F.text == "✅ Разблокировать")
@admin_required
async def unban_user_start(message: types.Message):
    user_states[message.from_user.id] = "unbanning_user"
    await message.answer("Введите ID пользователя для разблокировки:", reply_markup=ReplyKeyboardRemove())

@dp.message(F.text == "❌ Снять админа")
@admin_required
async def demote_user_start(message: types.Message):
    user_states[message.from_user.id] = "demoting_user"
    await message.answer("Введите ID пользователя для снятия прав администратора:", reply_markup=ReplyKeyboardRemove())

# Обработчики ввода ID пользователей для управления
@dp.message(F.text, lambda message: user_states.get(message.from_user.id) == "promoting_user")
async def promote_user_execute(message: types.Message):
    if not message.text.isdigit():
        await message.answer("❌ Введите корректный ID пользователя (число).")
        return

    target_user_id = int(message.text)
    admin_id = message.from_user.id

    try:
        cursor.execute("SELECT first_name, username FROM users WHERE user_id = ?", (target_user_id,))
        user = cursor.fetchone()

        if not user:
            await message.answer("❌ Пользователь не найден в базе данных.")
        else:
            cursor.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (target_user_id,))
            conn.commit()

            username = f"@{user[1]}" if user[1] else "без username"
            await message.answer(f"✅ Пользователь {user[0]} ({username}) назначен администратором.", reply_markup=get_user_management_keyboard())
            await log_action(admin_id, "Назначение администратора", f"Пользователь ID {target_user_id} назначен админом")

            # Уведомляем пользователя
            try:
                await bot.send_message(target_user_id, "🎉 Вам предоставлены права администратора!")
            except:
                pass

    except Exception as e:
        logger.error(f"Ошибка при назначении админа: {e}")
        await message.answer("❌ Ошибка при назначении администратора.")

    user_states[message.from_user.id] = None

@dp.message(F.text, lambda message: user_states.get(message.from_user.id) == "banning_user")
async def ban_user_execute(message: types.Message):
    if not message.text.isdigit():
        await message.answer("❌ Введите корректный ID пользователя (число).")
        return

    target_user_id = int(message.text)
    admin_id = message.from_user.id

    if target_user_id == MAIN_ADMIN_ID:
        await message.answer("❌ Нельзя заблокировать главного администратора.")
        user_states[message.from_user.id] = None
        return

    try:
        cursor.execute("SELECT first_name, username FROM users WHERE user_id = ?", (target_user_id,))
        user = cursor.fetchone()

        if not user:
            await message.answer("❌ Пользователь не найден в базе данных.")
        else:
            cursor.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (target_user_id,))
            conn.commit()

            username = f"@{user[1]}" if user[1] else "без username"
            await message.answer(f"🚫 Пользователь {user[0]} ({username}) заблокирован.", reply_markup=get_user_management_keyboard())
            await log_action(admin_id, "Блокировка пользователя", f"Пользователь ID {target_user_id} заблокирован")

            # Уведомляем пользователя
            try:
                await bot.send_message(target_user_id, "🚫 Ваш доступ к боту заблокирован администратором.")
            except:
                pass

    except Exception as e:
        logger.error(f"Ошибка при блокировке пользователя: {e}")
        await message.answer("❌ Ошибка при блокировке пользователя.")

    user_states[message.from_user.id] = None

@dp.message(F.text, lambda message: user_states.get(message.from_user.id) == "unbanning_user")
async def unban_user_execute(message: types.Message):
    if not message.text.isdigit():
        await message.answer("❌ Введите корректный ID пользователя (число).")
        return

    target_user_id = int(message.text)
    admin_id = message.from_user.id

    try:
        cursor.execute("SELECT first_name, username FROM users WHERE user_id = ?", (target_user_id,))
        user = cursor.fetchone()

        if not user:
            await message.answer("❌ Пользователь не найден в базе данных.")
        else:
            cursor.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (target_user_id,))
            conn.commit()

            username = f"@{user[1]}" if user[1] else "без username"
            await message.answer(f"✅ Пользователь {user[0]} ({username}) разблокирован.", reply_markup=get_user_management_keyboard())
            await log_action(admin_id, "Разблокировка пользователя", f"Пользователь ID {target_user_id} разблокирован")

            # Уведомляем пользователя
            try:
                await bot.send_message(target_user_id, "✅ Ваш доступ к боту восстановлен!")
            except:
                pass

    except Exception as e:
        logger.error(f"Ошибка при разблокировке пользователя: {e}")
        await message.answer("❌ Ошибка при разблокировке пользователя.")

    user_states[message.from_user.id] = None

@dp.message(F.text, lambda message: user_states.get(message.from_user.id) == "demoting_user")
async def demote_user_execute(message: types.Message):
    if not message.text.isdigit():
        await message.answer("❌ Введите корректный ID пользователя (число).")
        return

    target_user_id = int(message.text)
    admin_id = message.from_user.id

    if target_user_id == MAIN_ADMIN_ID:
        await message.answer("❌ Нельзя снять права у главного администратора.")
        user_states[message.from_user.id] = None
        return

    try:
        cursor.execute("SELECT first_name, username FROM users WHERE user_id = ?", (target_user_id,))
        user = cursor.fetchone()

        if not user:
            await message.answer("❌ Пользователь не найден в базе данных.")
        else:
            cursor.execute("UPDATE users SET is_admin = 0 WHERE user_id = ?", (target_user_id,))
            conn.commit()

            username = f"@{user[1]}" if user[1] else "без username"
            await message.answer(f"❌ У пользователя {user[0]} ({username}) сняты права администратора.", reply_markup=get_user_management_keyboard())
            await log_action(admin_id, "Снятие прав администратора", f"У пользователя ID {target_user_id} сняты права админа")

            # Уведомляем пользователя
            try:
                await bot.send_message(target_user_id, "❌ Ваши права администратора отозваны.")
            except:
                pass

    except Exception as e:
        logger.error(f"Ошибка при снятии прав администратора: {e}")
        await message.answer("❌ Ошибка при снятии прав администратора.")

    user_states[message.from_user.id] = None

# Навигация админ-панели
@dp.message(F.text == "🔙 Назад в админ-панель")
@admin_required
async def back_to_admin_panel(message: types.Message):
    await message.answer("👑 Панель администратора", reply_markup=get_admin_keyboard())

@dp.message(F.text == "🔙 Назад в главное меню")
async def back_to_main_menu_from_admin(message: types.Message):
    await message.answer("Главное меню:", reply_markup=get_main_keyboard(message.from_user.id))

# ===== ДОБАВЛЕНИЕ ТОВАРА =====
@dp.message(F.text == "📦 Добавить товар")
@access_required
async def add_product_start(message: types.Message):
    user_id = message.from_user.id
    user_states[user_id] = "adding_name"
    user_data[user_id] = {}
    await message.answer("Введите название товара:", reply_markup=ReplyKeyboardRemove())


@dp.message(F.text, lambda message: user_states.get(message.from_user.id) == "adding_name")
async def add_product_name(message: types.Message):
    user_id = message.from_user.id
    user_data[user_id]["name"] = message.text
    user_states[user_id] = "adding_quantity"
    await message.answer("Введите количество товара:")


@dp.message(F.text, lambda message: user_states.get(message.from_user.id) == "adding_quantity")
async def add_product_quantity(message: types.Message):
    user_id = message.from_user.id
    if not message.text.isdigit():
        await message.answer("❌ Ошибка! Введите число для количества.")
        return

    user_data[user_id]["quantity"] = int(message.text)
    user_states[user_id] = "adding_category"
    await message.answer("Введите категорию товара (или нажмите 'Пропустить'):",
                         reply_markup=ReplyKeyboardMarkup(
                             keyboard=[[KeyboardButton(text="Пропустить")]],
                             resize_keyboard=True
                         ))


@dp.message(F.text, lambda message: user_states.get(message.from_user.id) == "adding_category")
async def add_product_final(message: types.Message):
    user_id = message.from_user.id
    category = None if message.text == "Пропустить" else message.text

    try:
        cursor.execute(
            "INSERT INTO products (name, quantity, category) VALUES (?, ?, ?)",
            (user_data[user_id]["name"], user_data[user_id]["quantity"], category)
        )
        conn.commit()

        await message.answer(
            f"✅ Товар успешно добавлен!\n"
            f"Название: {user_data[user_id]['name']}\n"
            f"Количество: {user_data[user_id]['quantity']}\n"
            f"Категория: {category if category else 'не указана'}",
            reply_markup=get_main_keyboard(user_id)
        )

        # Логируем действие
        await log_action(user_id, "Добавление товара", f"{user_data[user_id]['name']} (кол-во: {user_data[user_id]['quantity']})")

        # Проверяем, не добавлен ли товар с низким запасом
        if user_data[user_id]["quantity"] < 10:
            await message.answer(
                f"⚠️ Внимание! Товар '{user_data[user_id]['name']}' добавлен с низким количеством: {user_data[user_id]['quantity']} шт.",
                reply_markup=get_main_keyboard(user_id)
            )
    except Exception as e:
        logger.error(f"Ошибка при добавлении товара: {e}")
        await message.answer("❌ Произошла ошибка при добавлении товара!", reply_markup=get_main_keyboard(user_id))
    finally:
        user_states[user_id] = None
        user_data[user_id] = {}


# ===== ПОИСК ТОВАРА (ПОЛНОСТЬЮ ПЕРЕРАБОТАННЫЙ) =====
@dp.message(F.text == "🔍 Поиск товара")
@access_required
async def search_product_start(message: types.Message):
    user_states[message.from_user.id] = "searching"
    await message.answer("Введите название товара или категории для поиска:", reply_markup=ReplyKeyboardRemove())


@dp.message(F.text, lambda message: user_states.get(message.from_user.id) == "searching")
async def search_product_execute(message: types.Message):
    user_id = message.from_user.id
    search_term = message.text.strip()  # Удаляем лишние пробелы

    try:
        # Получаем все товары для локального поиска
        cursor.execute("SELECT * FROM products")
        all_products = cursor.fetchall()

        if not all_products:
            await message.answer("📭 Склад пуст!", reply_markup=get_main_keyboard(user_id))
            user_states[user_id] = None
            return

        # Фильтруем товары без учета регистра
        found_products = []
        for product in all_products:
            name_match = search_term.lower() in product[1].lower() if product[1] else False
            category_match = search_term.lower() in product[3].lower() if product[3] else False

            if name_match or category_match:
                found_products.append(product)

        if not found_products:
            await message.answer(f"🔎 По запросу '{search_term}' товары не найдены",
                                 reply_markup=get_main_keyboard(user_id))
            user_states[user_id] = None
            return

        # Формируем ответ
        response = f"🔍 Результаты поиска ('{search_term}'):\n\n"
        for product in found_products:
            response += (f"{'⚠️' if product[2] < 10 else '🔹'} ID: {product[0]}\n"
                         f"Название: {product[1]}\n"
                         f"Количество: {product[2]}\n"
                         f"Категория: {product[3] if product[3] else 'не указана'}\n\n")

        # Разбиваем длинные сообщения
        if len(response) > 4000:
            for x in range(0, len(response), 4000):
                await message.answer(response[x:x + 4000])
        else:
            await message.answer(response, reply_markup=get_main_keyboard(user_id))

        # Логируем поиск
        await log_action(user_id, "Поиск товара", f"Запрос: '{search_term}', найдено: {len(found_products)}")

    except Exception as e:
        logger.error(f"Ошибка при поиске товара: {e}")
        await message.answer("❌ Произошла ошибка при поиске товара!", reply_markup=get_main_keyboard(user_id))
    finally:
        user_states[user_id] = None


# ===== РЕДАКТИРОВАНИЕ ТОВАРА =====
@dp.message(F.text == "✏️ Редактировать")
@access_required
async def edit_product_start(message: types.Message):
    # Получаем список товаров из базы
    cursor.execute("SELECT id, name, quantity FROM products")
    products = cursor.fetchall()

    if not products:
        await message.answer("📭 Склад пуст! Нечего редактировать.", reply_markup=get_main_keyboard(message.from_user.id))
        return

    # Создаем клавиатуру с кнопками товаров
    keyboard = []
    for product in products:
        keyboard.append([KeyboardButton(text=f"✏️ {product[1]} (ID: {product[0]}, Кол-во: {product[2]})")])

    keyboard.append([KeyboardButton(text="🔙 Назад")])

    await message.answer(
        "Выберите товар для редактирования:",
        reply_markup=ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
    )


# Обработчик выбора товара для редактирования
@dp.message(F.text.startswith("✏️ "))
async def edit_product_selected(message: types.Message):
    try:
        # Извлекаем ID из текста кнопки
        product_id = int(message.text.split("(ID: ")[1].split(",")[0])

        # Получаем информацию о товаре
        cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        product = cursor.fetchone()

        if not product:
            await message.answer("❌ Товар не найден!", reply_markup=get_main_keyboard(message.from_user.id))
            return

        # Сохраняем выбранный товар
        user_data[message.from_user.id] = {
            "edit_id": product_id,
            "current_name": product[1],
            "current_quantity": product[2],
            "current_category": product[3]
        }

        # Предлагаем выбрать что редактировать
        await message.answer(
            f"Выбран товар:\n"
            f"ID: {product[0]}\n"
            f"Название: {product[1]}\n"
            f"Количество: {product[2]}\n"
            f"Категория: {product[3] if product[3] else 'не указана'}\n\n"
            "Что хотите изменить?",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="🖊 Изменить название")],
                    [KeyboardButton(text="🔢 Изменить количество")],
                    [KeyboardButton(text="🏷 Изменить категорию")],
                    [KeyboardButton(text="🔙 Назад")]
                ],
                resize_keyboard=True
            )
        )

    except Exception as e:
        logger.error(f"Ошибка при выборе товара: {e}")
        await message.answer("❌ Ошибка при выборе товара!", reply_markup=get_main_keyboard(message.from_user.id))


# Обработчики выбора действия
@dp.message(F.text == "🖊 Изменить название")
async def edit_name_handler(message: types.Message):
    user_states[message.from_user.id] = "editing_name"
    await message.answer("Введите новое название:", reply_markup=ReplyKeyboardRemove())


@dp.message(F.text == "🔢 Изменить количество")
async def edit_quantity_handler(message: types.Message):
    user_states[message.from_user.id] = "editing_quantity"
    await message.answer("Введите новое количество:", reply_markup=ReplyKeyboardRemove())


@dp.message(F.text == "🏷 Изменить категорию")
async def edit_category_handler(message: types.Message):
    user_states[message.from_user.id] = "editing_category"
    await message.answer(
        "Введите новую категорию или 'удалить' чтобы удалить категорию:",
        reply_markup=ReplyKeyboardRemove()
    )


# Обработчики ввода новых значений
@dp.message(F.text, lambda message: user_states.get(message.from_user.id) == "editing_name")
async def save_new_name(message: types.Message):
    if message.text == "🔙 Отмена":
        await message.answer("Изменение названия отменено", reply_markup=get_main_keyboard(message.from_user.id))
    else:
        product_id = user_data[message.from_user.id]["edit_id"]
        cursor.execute("UPDATE products SET name = ? WHERE id = ?", (message.text, product_id))
        conn.commit()
        await message.answer(f"✅ Название изменено на: {message.text}", reply_markup=get_main_keyboard(message.from_user.id))
    user_states[message.from_user.id] = None


@dp.message(F.text, lambda message: user_states.get(message.from_user.id) == "editing_quantity")
async def save_new_quantity(message: types.Message):
    if message.text == "🔙 Отмена":
        await message.answer("Изменение количества отменено", reply_markup=get_main_keyboard(message.from_user.id))
    elif not message.text.isdigit():
        await message.answer("❌ Введите число!")
    else:
        product_id = user_data[message.from_user.id]["edit_id"]
        new_quantity = int(message.text)
        cursor.execute("UPDATE products SET quantity = ? WHERE id = ?", (new_quantity, product_id))
        conn.commit()

        response = f"✅ Количество изменено на: {new_quantity}"
        if new_quantity < 10:
            product_name = user_data[message.from_user.id]["current_name"]
            response += f"\n⚠️ Внимание! Товар '{product_name}' теперь имеет низкий запас: {new_quantity} шт."

        await message.answer(response, reply_markup=get_main_keyboard(message.from_user.id))
    user_states[message.from_user.id] = None


@dp.message(F.text, lambda message: user_states.get(message.from_user.id) == "editing_category")
async def save_new_category(message: types.Message):
    if message.text == "🔙 Отмена":
        await message.answer("Изменение категории отменено", reply_markup=get_main_keyboard(message.from_user.id))
    else:
        product_id = user_data[message.from_user.id]["edit_id"]
        new_category = None if message.text.lower() == "удалить" else message.text
        cursor.execute("UPDATE products SET category = ? WHERE id = ?", (new_category, product_id))
        conn.commit()
        action = "удалена" if new_category is None else "изменена"
        await message.answer(f"✅ Категория {action}", reply_markup=get_main_keyboard(message.from_user.id))
    user_states[message.from_user.id] = None


# ===== УДАЛЕНИЕ ТОВАРА =====
@dp.message(F.text == "❌ Удалить товар")
@access_required
async def delete_product_start(message: types.Message):
    # Получаем список товаров из базы
    cursor.execute("SELECT id, name FROM products")
    products = cursor.fetchall()

    if not products:
        await message.answer("📭 Склад пуст! Нечего удалять.", reply_markup=get_main_keyboard(message.from_user.id))
        return

    # Создаем клавиатуру с кнопками товаров
    keyboard = []
    for product in products:
        keyboard.append([KeyboardButton(text=f"❌ Удалить {product[1]} (ID: {product[0]})")])

    keyboard.append([KeyboardButton(text="🔙 Назад")])

    await message.answer(
        "Выберите товар для удаления:",
        reply_markup=ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
    )


# Обработчик выбора товара для удаления
@dp.message(F.text.startswith("❌ Удалить "))
async def delete_product_selected(message: types.Message):
    try:
        # Извлекаем ID из текста кнопки
        product_id = int(message.text.split("(ID: ")[1].rstrip(")"))

        # Получаем информацию о товаре
        cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        product = cursor.fetchone()

        if not product:
            await message.answer("❌ Товар не найден!", reply_markup=get_main_keyboard(message.from_user.id))
            return

        # Удаляем товар
        cursor.execute("DELETE FROM products WHERE id = ?", (product_id,))
        conn.commit()

        await message.answer(
            f"🗑 Товар успешно удален!\n"
            f"ID: {product[0]}\n"
            f"Название: {product[1]}\n"
            f"Количество: {product[2]}\n"
            f"Категория: {product[3] if product[3] else 'не указана'}",
            reply_markup=get_main_keyboard(message.from_user.id)
        )

        # Логируем действие удаления
        await log_action(message.from_user.id, "Удаление товара", f"{product[1]} (ID: {product[0]}, кол-во: {product[2]})")

    except Exception as e:
        logger.error(f"Ошибка при удалении товара: {e}")
        await message.answer("❌ Произошла ошибка при удалении товара!", reply_markup=get_main_keyboard(message.from_user.id))


# Обработчик кнопки "Назад"
@dp.message(F.text == "🔙 Назад")
async def back_to_main_menu(message: types.Message):
    await message.answer("Главное меню:", reply_markup=get_main_keyboard(message.from_user.id))


# ===== ВЫВОД СПИСКА ТОВАРОВ =====
@dp.message(F.text == "📊 Посмотреть склад")
@access_required
async def show_warehouse(message: types.Message):
    user_id = message.from_user.id
    user_states[user_id] = None

    try:
        # Получаем все товары
        cursor.execute("SELECT * FROM products ORDER BY quantity ASC")
        products = cursor.fetchall()

        if not products:
            await message.answer("📭 Склад пуст!", reply_markup=get_main_keyboard(message.from_user.id))
            return

        # Получаем товары с низким запасом (меньше 10)
        cursor.execute("SELECT * FROM products WHERE quantity < 10 ORDER BY quantity ASC")
        low_stock = cursor.fetchall()

        response = "📋 Список товаров:\n\n"
        for product in products:
            response += (
                f"{'⚠️' if product[2] < 10 else '🔹'} ID: {product[0]}\n"
                f"Название: {product[1]}\n"
                f"Количество: {product[2]}\n"
                f"Категория: {product[3] if product[3] else 'не указана'}\n"
                f"Добавлен: {product[4]}\n\n"
            )

        # Добавляем предупреждение о низких запасах
        if low_stock:
            warning = "🚨 Внимание! Заканчиваются следующие товары:\n\n"
            for product in low_stock:
                warning += (
                    f"▪️ {product[1]} (ID: {product[0]}) - осталось {product[2]} шт.\n"
                )
            response = warning + "\n" + response

        # Разбиваем сообщение на части, если оно слишком длинное
        max_length = 4000
        for i in range(0, len(response), max_length):
            await message.answer(response[i:i + max_length])

    except Exception as e:
        logger.error(f"Ошибка при выводе склада: {e}")
        await message.answer("❌ Произошла ошибка при получении данных склада!", reply_markup=get_main_keyboard(message.from_user.id))


# ===== КОМАНДА ДЛЯ ПРОВЕРКИ ЗАКАНЧИВАЮЩИХСЯ ТОВАРОВ =====
@dp.message(F.text == "🚨 Проверить остатки")
@access_required
async def check_low_stock(message: types.Message):
    try:
        cursor.execute("SELECT * FROM products WHERE quantity < 10 ORDER BY quantity ASC")
        low_stock = cursor.fetchall()

        if not low_stock:
            await message.answer("✅ Все товары в достаточном количестве (10+ шт.)", reply_markup=get_main_keyboard(message.from_user.id))
            return

        response = "🚨 Товары с низким запасом (<10 шт.):\n\n"
        for product in low_stock:
            response += (
                f"▪️ ID: {product[0]}\n"
                f"Название: {product[1]}\n"
                f"Осталось: {product[2]} шт.\n"
                f"Категория: {product[3] if product[3] else 'не указана'}\n\n"
            )

        await message.answer(response, reply_markup=get_main_keyboard(message.from_user.id))

    except Exception as e:
        logger.error(f"Ошибка при проверке остатков: {e}")
        await message.answer("❌ Произошла ошибка при проверке остатков!", reply_markup=get_main_keyboard(message.from_user.id))


# ===== ЭКСПОРТ В EXCEL (ПЕРЕРАБОТАННЫЙ) =====
@dp.message(F.text == "📥 Экспорт в Excel")
@access_required
async def export_to_excel(message: types.Message):
    try:
        # Получаем данные из базы
        cursor.execute("SELECT id, name, quantity, category, added_date FROM products")
        columns = [column[0] for column in cursor.description]
        data = cursor.fetchall()

        if not data:
            await message.answer("📭 Склад пуст! Нет данных для экспорта.", reply_markup=get_main_keyboard(message.from_user.id))
            return

        # Создаем Excel-файл в памяти
        output = BytesIO()

        # Создаем книгу Excel
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Склад"

        # Записываем заголовки
        sheet.append(columns)

        # Записываем данные
        for row in data:
            sheet.append(row)
            if row[2] < 10:  # Если количество < 10
                # Для совместимости пропускаем комментарии
                pass

        # Сохраняем в буфер
        workbook.save(output)
        output.seek(0)  # Важно: переводим указатель в начало

        # Подготавливаем файл для отправки
        file_data = output.getvalue()
        filename = f"склад_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.xlsx"

        # Создаем объект файла
        excel_file = BufferedInputFile(
            file=file_data,
            filename=filename
        )

        # Отправляем файл
        await message.answer_document(
            document=excel_file,
            caption="📊 Экспорт данных склада в Excel",
            reply_markup=get_main_keyboard(message.from_user.id)
        )

    except Exception as e:
        logger.error(f"Ошибка при экспорте: {str(e)}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при экспорте данных!\n"
            f"Ошибка: {str(e)}",
            reply_markup=get_main_keyboard(message.from_user.id)
        )
    finally:
        # Всегда закрываем буфер
        if 'output' in locals():
            output.close()


# ===== ОБРАБОТЧИКИ ДЛЯ ГРУПП И НЕИЗВЕСТНЫХ КОМАНД =====

# Обработчик для групп (игнорирует обычные сообщения)
@dp.message(F.chat.type.in_({"group", "supergroup"}))
async def handle_group_messages(message: types.Message):
    pass  # Игнорируем обычные сообщения в группах

# Обработчик неизвестных команд в личных чатах
@dp.message(F.chat.type == "private")
@access_required
async def unknown_command(message: types.Message):
    user_id = message.from_user.id
    await message.answer(
        "❌ Неизвестная команда. Возвращаю вас в главное меню.",
        reply_markup=get_main_keyboard(user_id)
    )
    await log_action(user_id, "Неизвестная команда", f"Введен текст: {message.text}")

# ===== ЗАПУСК БОТА =====
async def main():
    # Проверка базы при запуске
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='products'")
    table_exists = cursor.fetchone()
    logger.info(f"Таблица 'products' существует: {bool(table_exists)}")

    cursor.execute("SELECT COUNT(*) FROM products")
    count = cursor.fetchone()[0]
    logger.info(f"Количество товаров в базе при запуске: {count}")

    # Проверяем товары с низким запасом при запуске
    cursor.execute("SELECT COUNT(*) FROM products WHERE quantity < 10")
    low_stock_count = cursor.fetchone()[0]
    if low_stock_count > 0:
        logger.warning(f"Внимание! В базе {low_stock_count} товаров с низким запасом (<10 шт.)")

    logger.info("🤖 Складской бот запущен и готов к работе!")

    try:
        # Запускаем бота
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logger.info("⏹️ Получен сигнал остановки (Ctrl+C)")
    except Exception as e:
        logger.error(f"❌ Ошибка при работе бота: {e}")
    finally:
        logger.info("🛑 EcoSystemSoraBot остановлен")
        # Закрываем соединение с базой данных
        conn.close()
        logger.info("📦 Соединение с базой данных закрыто")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⏹️ Программа прервана пользователем")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
    finally:
        logger.info("👋 Программа завершена")