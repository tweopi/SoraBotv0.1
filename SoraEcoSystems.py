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
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(token="8143304952:AAHm-ha-Cb2vqOHeOyWGO1B4sdS6wbzBiBQ")
dp = Dispatcher()

# Состояния пользователей
user_states = {}
user_data = {}

## ===== НАСТРОЙКА БАЗЫ ДАННЫХ =====
BASE_DIR = Path(__file__).parent
DB_DIR = BASE_DIR / "database"
EXPORT_DIR = BASE_DIR / "exports"
REPORTS_DIR = BASE_DIR / "reports"

# Создаем необходимые директории
DB_DIR.mkdir(exist_ok=True)
EXPORT_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)

DB_PATH = DB_DIR / "SoraClub.db"  # База данных теперь в папке /database

# Подключение к SQLite
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

# Создаем таблицы
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

cursor.execute('''
               CREATE TABLE IF NOT EXISTS shift_reports
               (
                   id
                   INTEGER
                   PRIMARY
                   KEY
                   AUTOINCREMENT,
                   user_id
                   INTEGER
                   NOT
                   NULL,
                   report_date
                   DATE
                   NOT
                   NULL,
                   total
                   REAL
                   NOT
                   NULL,
                   cash
                   REAL
                   NOT
                   NULL,
                   card
                   REAL
                   NOT
                   NULL,
                   bar
                   REAL
                   NOT
                   NULL,
                   hookah
                   REAL
                   NOT
                   NULL,
                   expenses
                   REAL
                   NOT
                   NULL,
                   balance
                   REAL
                   NOT
                   NULL,
                   timestamp
                   TIMESTAMP
                   DEFAULT
                   CURRENT_TIMESTAMP
               )
               ''')

conn.commit()

# ID главного администратора
MAIN_ADMIN_ID = 7873867301


# ===== ФУНКЦИЯ ПРОВЕРКИ РЕГИСТРАЦИИ ПОЛЬЗОВАТЕЛЯ =====
def is_registered(user_id):
    try:
        cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"Ошибка проверки регистрации пользователя {user_id}: {e}")
        return False


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
            logger.info(f"Зарегистрирован новый пользователь: ID={user_id}, Имя={first_name}, Админ={is_admin}")
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
    except Exception as e:
        logger.error(f"Ошибка проверки прав администратора для {user_id}: {e}")
        return False


# Функция для проверки бана пользователя
def is_banned(user_id):
    try:
        cursor.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        return result and result[0] == 1
    except Exception as e:
        logger.error(f"Ошибка проверки бана для {user_id}: {e}")
        return False


# Функция для логирования действий
async def log_action(user_id, action, details=""):
    try:
        cursor.execute(
            "INSERT INTO action_logs (user_id, action, details) VALUES (?, ?, ?)",
            (user_id, action, details)
        )
        conn.commit()
        logger.info(f"Действие пользователя {user_id}: {action} - {details}")

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
        [KeyboardButton(text="📊 Склад")],
        [KeyboardButton(text="📝 Отчёт по смене")],
        [KeyboardButton(text="📥 Экспорт в Excel")]
    ]

    if is_admin(user_id):
        keyboard.append([KeyboardButton(text="👑 Админ-панель")])

    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_warehouse_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📦 Добавить товар")],
            [KeyboardButton(text="📋 Посмотреть склад"), KeyboardButton(text="🔍 Поиск товара")],
            [KeyboardButton(text="✏️ Редактировать"), KeyboardButton(text="❌ Удалить товар")],
            [KeyboardButton(text="🚨 Проверить остатки")],
            [KeyboardButton(text="🔙 Назад в главное меню")]
        ],
        resize_keyboard=True
    )


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


def get_report_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Создать отчёт")],
            [KeyboardButton(text="🔄 Обновить отчёт")],
            [KeyboardButton(text="📅 История отчётов")],
            [KeyboardButton(text="🔙 Назад в главное меню")]
        ],
        resize_keyboard=True
    )


# ===== КЛАВИАТУРА ОТМЕНЫ =====
def get_cancel_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True
    )


# ===== ОБНОВЛЕННЫЙ MIDDLEWARE ДЛЯ ПРОВЕРКИ ДОСТУПА =====
def access_required(func):
    async def wrapper(message: types.Message):
        user_id = message.from_user.id

        # Проверка регистрации
        if not is_registered(user_id):
            await message.answer("❌ Вы не зарегистрированы в системе. Обратитесь к администратору.")
            logger.warning(f"Попытка доступа незарегистрированного пользователя: {user_id}")
            return

        if is_banned(user_id):
            await message.answer("❌ Ваш доступ к боту заблокирован.")
            return
        return await func(message)

    return wrapper


def admin_required(func):
    async def wrapper(message: types.Message):
        user_id = message.from_user.id

        # Проверка регистрации
        if not is_registered(user_id):
            await message.answer("❌ Вы не зарегистрированы в системе. Обратитесь к администратору.")
            return

        if is_banned(user_id):
            await message.answer("❌ Ваш доступ к боту заблокирован.")
            return
        if not is_admin(user_id):
            await message.answer("❌ У вас нет прав администратора для выполнения этого действия.")
            return
        return await func(message)

    return wrapper


# ===== КОМАНДА /start =====
@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name

    # Автоматическая регистрация главного администратора
    if user_id == MAIN_ADMIN_ID and not is_registered(user_id):
        cursor.execute(
            "INSERT INTO users (user_id, username, first_name, is_admin) VALUES (?, ?, ?, ?)",
            (user_id, username, first_name, 1)
        )
        conn.commit()
        logger.info(f"Главный администратор зарегистрирован: {user_id}")

    # Проверяем, зарегистрирован ли пользователь
    if not is_registered(user_id):
        await message.answer(
            "❌ Вы не зарегистрированы в системе.\n"
            "Обратитесь к администратору для получения доступа."
        )
        logger.warning(f"Попытка доступа незарегистрированного пользователя: {user_id}")
        return

    # Проверяем, заблокирован ли пользователь
    if is_banned(user_id):
        await message.answer("❌ Ваш доступ к боту заблокирован администратором.")
        return

    # Регистрируем пользователя (если это новый пользователь)
    is_new_user = register_user(user_id, username, first_name)

    user_states[user_id] = None
    user_data[user_id] = {}

    welcome_text = "🛒 Добро пожаловать в складской бот!\n"
    if is_new_user:
        welcome_text += "✅ Вы успешно зарегистрированы!\n"
        await log_action(user_id, "Новый пользователь", f"Первый запуск бота")

    welcome_text += "Выберите действие из меню ниже:"

    await message.answer(welcome_text, reply_markup=get_main_keyboard(user_id))


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
        cursor.execute(
            "SELECT user_id, username, first_name, is_admin, is_banned, added_date FROM users ORDER BY added_date DESC")
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
                await message.answer(response[i:i + 4000])
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

        # Статистика отчетов
        cursor.execute("SELECT COUNT(*) FROM shift_reports")
        total_reports = cursor.fetchone()[0]

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
            f"📝 Отчеты:\n"
            f"└ Всего отчетов: {total_reports}\n\n"
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
                await message.answer(response[i:i + 4000])
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
    await message.answer("Введите ID пользователя для назначения администратором:", reply_markup=get_cancel_keyboard())


@dp.message(F.text == "🚫 Заблокировать")
@admin_required
async def ban_user_start(message: types.Message):
    user_states[message.from_user.id] = "banning_user"
    await message.answer("Введите ID пользователя для блокировки:", reply_markup=get_cancel_keyboard())


@dp.message(F.text == "✅ Разблокировать")
@admin_required
async def unban_user_start(message: types.Message):
    user_states[message.from_user.id] = "unbanning_user"
    await message.answer("Введите ID пользователя для разблокировки:", reply_markup=get_cancel_keyboard())


@dp.message(F.text == "❌ Снять админа")
@admin_required
async def demote_user_start(message: types.Message):
    user_states[message.from_user.id] = "demoting_user"
    await message.answer("Введите ID пользователя для снятия прав администратора:", reply_markup=get_cancel_keyboard())


# Обработчики ввода ID пользователей для управления
@dp.message(F.text, lambda message: user_states.get(message.from_user.id) == "promoting_user")
async def promote_user_execute(message: types.Message):
    if message.text == "❌ Отмена":
        user_states[message.from_user.id] = None
        await message.answer("❌ Назначение администратора отменено", reply_markup=get_user_management_keyboard())
        return

    if not message.text.isdigit():
        await message.answer("❌ Введите корректный ID пользователя (число).", reply_markup=get_cancel_keyboard())
        return

    target_user_id = int(message.text)
    admin_id = message.from_user.id

    try:
        cursor.execute("SELECT first_name, username FROM users WHERE user_id = ?", (target_user_id,))
        user = cursor.fetchone()

        if not user:
            await message.answer("❌ Пользователь не найден в базе данных.", reply_markup=get_cancel_keyboard())
        else:
            cursor.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (target_user_id,))
            conn.commit()

            username = f"@{user[1]}" if user[1] else "без username"
            await message.answer(f"✅ Пользователь {user[0]} ({username}) назначен администратором.",
                                 reply_markup=get_user_management_keyboard())
            await log_action(admin_id, "Назначение администратора",
                             f"Пользователь ID {target_user_id} назначен админом")

            # Уведомляем пользователя
            try:
                await bot.send_message(target_user_id, "🎉 Вам предоставлены права администратора!")
            except:
                pass

    except Exception as e:
        logger.error(f"Ошибка при назначении админа: {e}")
        await message.answer("❌ Ошибка при назначении администратора.", reply_markup=get_cancel_keyboard())
    finally:
        user_states[message.from_user.id] = None


@dp.message(F.text, lambda message: user_states.get(message.from_user.id) == "banning_user")
async def ban_user_execute(message: types.Message):
    if message.text == "❌ Отмена":
        user_states[message.from_user.id] = None
        await message.answer("❌ Блокировка пользователя отменена", reply_markup=get_user_management_keyboard())
        return

    if not message.text.isdigit():
        await message.answer("❌ Введите корректный ID пользователя (число).", reply_markup=get_cancel_keyboard())
        return

    target_user_id = int(message.text)
    admin_id = message.from_user.id

    if target_user_id == MAIN_ADMIN_ID:
        await message.answer("❌ Нельзя заблокировать главного администратора.", reply_markup=get_cancel_keyboard())
        user_states[message.from_user.id] = None
        return

    try:
        cursor.execute("SELECT first_name, username FROM users WHERE user_id = ?", (target_user_id,))
        user = cursor.fetchone()

        if not user:
            await message.answer("❌ Пользователь не найден в базе данных.", reply_markup=get_cancel_keyboard())
        else:
            cursor.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (target_user_id,))
            conn.commit()

            username = f"@{user[1]}" if user[1] else "без username"
            await message.answer(f"🚫 Пользователь {user[0]} ({username}) заблокирован.",
                                 reply_markup=get_user_management_keyboard())
            await log_action(admin_id, "Блокировка пользователя", f"Пользователь ID {target_user_id} заблокирован")

            # Уведомляем пользователя
            try:
                await bot.send_message(target_user_id, "🚫 Ваш доступ к боту заблокирован администратором.")
            except:
                pass

    except Exception as e:
        logger.error(f"Ошибка при блокировке пользователя: {e}")
        await message.answer("❌ Ошибка при блокировке пользователя.", reply_markup=get_cancel_keyboard())
    finally:
        user_states[message.from_user.id] = None


@dp.message(F.text, lambda message: user_states.get(message.from_user.id) == "unbanning_user")
async def unban_user_execute(message: types.Message):
    if message.text == "❌ Отмена":
        user_states[message.from_user.id] = None
        await message.answer("❌ Разблокировка пользователя отменена", reply_markup=get_user_management_keyboard())
        return

    if not message.text.isdigit():
        await message.answer("❌ Введите корректный ID пользователя (число).", reply_markup=get_cancel_keyboard())
        return

    target_user_id = int(message.text)
    admin_id = message.from_user.id

    try:
        cursor.execute("SELECT first_name, username FROM users WHERE user_id = ?", (target_user_id,))
        user = cursor.fetchone()

        if not user:
            await message.answer("❌ Пользователь не найден в базе данных.", reply_markup=get_cancel_keyboard())
        else:
            cursor.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (target_user_id,))
            conn.commit()

            username = f"@{user[1]}" if user[1] else "без username"
            await message.answer(f"✅ Пользователь {user[0]} ({username}) разблокирован.",
                                 reply_markup=get_user_management_keyboard())
            await log_action(admin_id, "Разблокировка пользователя", f"Пользователь ID {target_user_id} разблокирован")

            # Уведомляем пользователя
            try:
                await bot.send_message(target_user_id, "✅ Ваш доступ к боту восстановлен!")
            except:
                pass

    except Exception as e:
        logger.error(f"Ошибка при разблокировке пользователя: {e}")
        await message.answer("❌ Ошибка при разблокировке пользователя.", reply_markup=get_cancel_keyboard())
    finally:
        user_states[message.from_user.id] = None


@dp.message(F.text, lambda message: user_states.get(message.from_user.id) == "demoting_user")
async def demote_user_execute(message: types.Message):
    if message.text == "❌ Отмена":
        user_states[message.from_user.id] = None
        await message.answer("❌ Снятие прав администратора отменено", reply_markup=get_user_management_keyboard())
        return

    if not message.text.isdigit():
        await message.answer("❌ Введите корректный ID пользователя (число).", reply_markup=get_cancel_keyboard())
        return

    target_user_id = int(message.text)
    admin_id = message.from_user.id

    if target_user_id == MAIN_ADMIN_ID:
        await message.answer("❌ Нельзя снять права у главного администратора.", reply_markup=get_cancel_keyboard())
        user_states[message.from_user.id] = None
        return

    try:
        cursor.execute("SELECT first_name, username FROM users WHERE user_id = ?", (target_user_id,))
        user = cursor.fetchone()

        if not user:
            await message.answer("❌ Пользователь не найден в базе данных.", reply_markup=get_cancel_keyboard())
        else:
            cursor.execute("UPDATE users SET is_admin = 0 WHERE user_id = ?", (target_user_id,))
            conn.commit()

            username = f"@{user[1]}" if user[1] else "без username"
            await message.answer(f"❌ У пользователя {user[0]} ({username}) сняты права администратора.",
                                 reply_markup=get_user_management_keyboard())
            await log_action(admin_id, "Снятие прав администратора",
                             f"У пользователя ID {target_user_id} сняты права админа")

            # Уведомляем пользователя
            try:
                await bot.send_message(target_user_id, "❌ Ваши права администратора отозваны.")
            except:
                pass

    except Exception as e:
        logger.error(f"Ошибка при снятии прав администратора: {e}")
        await message.answer("❌ Ошибка при снятии прав администратора.", reply_markup=get_cancel_keyboard())
    finally:
        user_states[message.from_user.id] = None


# Навигация админ-панели
@dp.message(F.text == "🔙 Назад в админ-панель")
@admin_required
async def back_to_admin_panel(message: types.Message):
    await message.answer("👑 Панель администратора", reply_markup=get_admin_keyboard())


@dp.message(F.text == "🔙 Назад в главное меню")
async def back_to_main_menu_from_admin(message: types.Message):
    await message.answer("Главное меню:", reply_markup=get_main_keyboard(message.from_user.id))


# ===== Обработчик входа в меню склада =====
@dp.message(F.text == "📊 Склад")
@access_required
async def warehouse_menu(message: types.Message):
    await message.answer(
        "📊 Управление складом\n"
        "Выберите действие:",
        reply_markup=get_warehouse_keyboard()
    )


# ===== ДОБАВЛЕНИЕ ТОВАРА =====
@dp.message(F.text == "📦 Добавить товар")
@access_required
async def add_product_start(message: types.Message):
    user_id = message.from_user.id
    user_states[user_id] = "adding_name"
    user_data[user_id] = {}
    await message.answer("Введите название товара:", reply_markup=get_cancel_keyboard())


@dp.message(F.text, lambda message: user_states.get(message.from_user.id) == "adding_name")
async def add_product_name(message: types.Message):
    if message.text == "❌ Отмена":
        user_states[message.from_user.id] = None
        user_data[message.from_user.id] = {}
        await message.answer("❌ Добавление товара отменено", reply_markup=get_warehouse_keyboard())
        return

    user_id = message.from_user.id
    user_data[user_id]["name"] = message.text
    user_states[user_id] = "adding_quantity"
    await message.answer("Введите количество товара:", reply_markup=get_cancel_keyboard())


@dp.message(F.text, lambda message: user_states.get(message.from_user.id) == "adding_quantity")
async def add_product_quantity(message: types.Message):
    if message.text == "❌ Отмена":
        user_states[message.from_user.id] = None
        user_data[message.from_user.id] = {}
        await message.answer("❌ Добавление товара отменено", reply_markup=get_warehouse_keyboard())
        return

    user_id = message.from_user.id
    if not message.text.isdigit():
        await message.answer("❌ Ошибка! Введите число для количества.", reply_markup=get_cancel_keyboard())
        return

    user_data[user_id]["quantity"] = int(message.text)
    user_states[user_id] = "adding_category"
    await message.answer(
        "Введите категорию товара (или нажмите 'Пропустить'):",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Пропустить")],
                [KeyboardButton(text="❌ Отмена")]
            ],
            resize_keyboard=True
        )
    )


@dp.message(F.text, lambda message: user_states.get(message.from_user.id) == "adding_category")
async def add_product_final(message: types.Message):
    if message.text == "❌ Отмена":
        user_states[message.from_user.id] = None
        user_data[message.from_user.id] = {}
        await message.answer("❌ Добавление товара отменено", reply_markup=get_warehouse_keyboard())
        return

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
            reply_markup=get_warehouse_keyboard()
        )

        await log_action(user_id, "Добавление товара",
                         f"{user_data[user_id]['name']} (кол-во: {user_data[user_id]['quantity']})")

        if user_data[user_id]["quantity"] < 10:
            await message.answer(
                f"⚠️ Внимание! Товар '{user_data[user_id]['name']}' добавлен с низким количеством: {user_data[user_id]['quantity']} шт.",
                reply_markup=get_warehouse_keyboard()
            )
    except Exception as e:
        logger.error(f"Ошибка при добавлении товара: {e}")
        await message.answer("❌ Произошла ошибка при добавлении товара!", reply_markup=get_warehouse_keyboard())
    finally:
        user_states[user_id] = None
        user_data[user_id] = {}


# ===== ПОИСК ТОВАРА =====
@dp.message(F.text == "🔍 Поиск товара")
@access_required
async def search_product_start(message: types.Message):
    user_states[message.from_user.id] = "searching"
    await message.answer("Введите название товара или категории для поиска:", reply_markup=get_cancel_keyboard())


@dp.message(F.text, lambda message: user_states.get(message.from_user.id) == "searching")
async def search_product_execute(message: types.Message):
    if message.text == "❌ Отмена":
        user_states[message.from_user.id] = None
        await message.answer("❌ Поиск товара отменен", reply_markup=get_warehouse_keyboard())
        return

    user_id = message.from_user.id
    search_term = message.text.strip()

    try:
        cursor.execute("SELECT * FROM products")
        all_products = cursor.fetchall()

        if not all_products:
            await message.answer("📭 Склад пуст!", reply_markup=get_warehouse_keyboard())
            user_states[user_id] = None
            return

        found_products = []
        for product in all_products:
            name_match = search_term.lower() in product[1].lower() if product[1] else False
            category_match = search_term.lower() in product[3].lower() if product[3] else False

            if name_match or category_match:
                found_products.append(product)

        if not found_products:
            await message.answer(f"🔎 По запросу '{search_term}' товары не найдены",
                                 reply_markup=get_warehouse_keyboard())
            user_states[user_id] = None
            return

        response = f"🔍 Результаты поиска ('{search_term}'):\n\n"
        for product in found_products:
            response += (f"{'⚠️' if product[2] < 10 else '🔹'} ID: {product[0]}\n"
                         f"Название: {product[1]}\n"
                         f"Количество: {product[2]}\n"
                         f"Категория: {product[3] if product[3] else 'не указана'}\n\n")

        if len(response) > 4000:
            for x in range(0, len(response), 4000):
                await message.answer(response[x:x + 4000])
        else:
            await message.answer(response, reply_markup=get_warehouse_keyboard())

        await log_action(user_id, "Поиск товара", f"Запрос: '{search_term}', найдено: {len(found_products)}")

    except Exception as e:
        logger.error(f"Ошибка при поиске товара: {e}")
        await message.answer("❌ Произошла ошибка при поиске товара!", reply_markup=get_warehouse_keyboard())
    finally:
        user_states[user_id] = None


# ===== РЕДАКТИРОВАНИЕ ТОВАРА =====
@dp.message(F.text == "✏️ Редактировать")
@access_required
async def edit_product_start(message: types.Message):
    cursor.execute("SELECT id, name, quantity FROM products")
    products = cursor.fetchall()

    if not products:
        await message.answer("📭 Склад пуст! Нечего редактировать.", reply_markup=get_warehouse_keyboard())
        return

    keyboard = []
    for product in products:
        keyboard.append([KeyboardButton(text=f"✏️ {product[1]} (ID: {product[0]}, Кол-во: {product[2]})")])

    keyboard.append([KeyboardButton(text="🔙 Назад")])

    await message.answer(
        "Выберите товар для редактирования:",
        reply_markup=ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
    )


@dp.message(F.text.startswith("✏️ "))
async def edit_product_selected(message: types.Message):
    try:
        product_id = int(message.text.split("(ID: ")[1].split(",")[0])
        cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        product = cursor.fetchone()

        if not product:
            await message.answer("❌ Товар не найден!", reply_markup=get_warehouse_keyboard())
            return

        user_data[message.from_user.id] = {
            "edit_id": product_id,
            "current_name": product[1],
            "current_quantity": product[2],
            "current_category": product[3]
        }

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
                    [KeyboardButton(text="🔙 К списку товаров")]  # Измененная кнопка
                ],
                resize_keyboard=True
            )
        )

    except Exception as e:
        logger.error(f"Ошибка при выборе товара: {e}")
        await message.answer("❌ Ошибка при выборе товара!", reply_markup=get_warehouse_keyboard())


# ===== ОБРАБОТЧИК ДЛЯ КНОПКИ "🔙 К СПИСКУ ТОВАРОВ" =====
@dp.message(F.text == "🔙 К списку товаров")
async def back_to_products_list(message: types.Message):
    # Вызываем функцию выбора товара для редактирования
    await edit_product_start(message)


@dp.message(F.text == "🖊 Изменить название")
async def edit_name_handler(message: types.Message):
    user_states[message.from_user.id] = "editing_name"
    await message.answer("Введите новое название:", reply_markup=get_cancel_keyboard())


@dp.message(F.text == "🔢 Изменить количество")
async def edit_quantity_handler(message: types.Message):
    user_states[message.from_user.id] = "editing_quantity"
    await message.answer("Введите новое количество:", reply_markup=get_cancel_keyboard())


@dp.message(F.text == "🏷 Изменить категорию")
async def edit_category_handler(message: types.Message):
    user_states[message.from_user.id] = "editing_category"
    await message.answer(
        "Введите новую категорию или 'удалить' чтобы удалить категорию:",
        reply_markup=get_cancel_keyboard()
    )


@dp.message(F.text, lambda message: user_states.get(message.from_user.id) == "editing_name")
async def save_new_name(message: types.Message):
    if message.text == "❌ Отмена":
        user_states[message.from_user.id] = None
        await message.answer("❌ Изменение названия отменено", reply_markup=get_warehouse_keyboard())
        return

    product_id = user_data[message.from_user.id]["edit_id"]
    cursor.execute("UPDATE products SET name = ? WHERE id = ?", (message.text, product_id))
    conn.commit()
    await message.answer(f"✅ Название изменено на: {message.text}", reply_markup=get_warehouse_keyboard())
    user_states[message.from_user.id] = None


@dp.message(F.text, lambda message: user_states.get(message.from_user.id) == "editing_quantity")
async def save_new_quantity(message: types.Message):
    if message.text == "❌ Отмена":
        user_states[message.from_user.id] = None
        await message.answer("❌ Изменение количества отменено", reply_markup=get_warehouse_keyboard())
        return

    if not message.text.isdigit():
        await message.answer("❌ Введите число!", reply_markup=get_cancel_keyboard())
        return

    product_id = user_data[message.from_user.id]["edit_id"]
    new_quantity = int(message.text)
    cursor.execute("UPDATE products SET quantity = ? WHERE id = ?", (new_quantity, product_id))
    conn.commit()

    response = f"✅ Количество изменено на: {new_quantity}"
    if new_quantity < 10:
        product_name = user_data[message.from_user.id]["current_name"]
        response += f"\n⚠️ Внимание! Товар '{product_name}' теперь имеет низкий запас: {new_quantity} шт."

    await message.answer(response, reply_markup=get_warehouse_keyboard())
    user_states[message.from_user.id] = None


@dp.message(F.text, lambda message: user_states.get(message.from_user.id) == "editing_category")
async def save_new_category(message: types.Message):
    if message.text == "❌ Отмена":
        user_states[message.from_user.id] = None
        await message.answer("❌ Изменение категории отменено", reply_markup=get_warehouse_keyboard())
        return

    product_id = user_data[message.from_user.id]["edit_id"]
    new_category = None if message.text.lower() == "удалить" else message.text
    cursor.execute("UPDATE products SET category = ? WHERE id = ?", (new_category, product_id))
    conn.commit()
    action = "удалена" if new_category is None else "изменена"
    await message.answer(f"✅ Категория {action}", reply_markup=get_warehouse_keyboard())
    user_states[message.from_user.id] = None


# ===== УДАЛЕНИЕ ТОВАРА =====
@dp.message(F.text == "❌ Удалить товар")
@access_required
async def delete_product_start(message: types.Message):
    cursor.execute("SELECT id, name FROM products")
    products = cursor.fetchall()

    if not products:
        await message.answer("📭 Склад пуст! Нечего удалять.", reply_markup=get_warehouse_keyboard())
        return

    keyboard = []
    for product in products:
        keyboard.append([KeyboardButton(text=f"❌ Удалить {product[1]} (ID: {product[0]})")])

    keyboard.append([KeyboardButton(text="🔙 Назад")])

    await message.answer(
        "Выберите товар для удаления:",
        reply_markup=ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
    )


@dp.message(F.text.startswith("❌ Удалить "))
async def delete_product_selected(message: types.Message):
    try:
        product_id = int(message.text.split("(ID: ")[1].rstrip(")"))
        cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        product = cursor.fetchone()

        if not product:
            await message.answer("❌ Товар не найден!", reply_markup=get_warehouse_keyboard())
            return

        cursor.execute("DELETE FROM products WHERE id = ?", (product_id,))
        conn.commit()

        await message.answer(
            f"🗑 Товар успешно удален!\n"
            f"ID: {product[0]}\n"
            f"Название: {product[1]}\n"
            f"Количество: {product[2]}\n"
            f"Категория: {product[3] if product[3] else 'не указана'}",
            reply_markup=get_warehouse_keyboard()
        )

        await log_action(message.from_user.id, "Удаление товара",
                         f"{product[1]} (ID: {product[0]}, кол-во: {product[2]})")

    except Exception as e:
        logger.error(f"Ошибка при удалении товара: {e}")
        await message.answer("❌ Произошла ошибка при удалении товара!", reply_markup=get_warehouse_keyboard())


# ===== ВЫВОД СПИСКА ТОВАРОВ =====
@dp.message(F.text == "📋 Посмотреть склад")
@access_required
async def show_warehouse(message: types.Message):
    user_id = message.from_user.id
    user_states[user_id] = None

    try:
        cursor.execute("SELECT * FROM products ORDER BY quantity ASC")
        products = cursor.fetchall()

        if not products:
            await message.answer("📭 Склад пуст!", reply_markup=get_warehouse_keyboard())
            return

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

        if low_stock:
            warning = "🚨 Внимание! Заканчиваются следующие товары:\n\n"
            for product in low_stock:
                warning += (
                    f"▪️ {product[1]} (ID: {product[0]}) - осталось {product[2]} шт.\n"
                )
            response = warning + "\n" + response

        max_length = 4000
        for i in range(0, len(response), max_length):
            await message.answer(response[i:i + max_length])

    except Exception as e:
        logger.error(f"Ошибка при выводе склада: {e}")
        await message.answer("❌ Произошла ошибка при получении данных склада!", reply_markup=get_warehouse_keyboard())


# ===== ПРОВЕРКА ЗАКАНЧИВАЮЩИХСЯ ТОВАРОВ =====
@dp.message(F.text == "🚨 Проверить остатки")
@access_required
async def check_low_stock(message: types.Message):
    try:
        cursor.execute("SELECT * FROM products WHERE quantity < 10 ORDER BY quantity ASC")
        low_stock = cursor.fetchall()

        if not low_stock:
            await message.answer("✅ Все товары в достаточном количестве (10+ шт.)",
                                 reply_markup=get_warehouse_keyboard())
            return

        response = "🚨 Товары с низким запасом (<10 шт.):\n\n"
        for product in low_stock:
            response += (
                f"▪️ ID: {product[0]}\n"
                f"Название: {product[1]}\n"
                f"Осталось: {product[2]} шт.\n"
                f"Категория: {product[3] if product[3] else 'не указана'}\n\n"
            )

        await message.answer(response, reply_markup=get_warehouse_keyboard())

    except Exception as e:
        logger.error(f"Ошибка при проверке остатков: {e}")
        await message.answer("❌ Произошла ошибка при проверке остатков!", reply_markup=get_warehouse_keyboard())


# ===== ЭКСПОРТ В EXCEL =====
@dp.message(F.text == "📥 Экспорт в Excel")
@access_required
async def export_to_excel(message: types.Message):
    try:
        cursor.execute("SELECT id, name, quantity, category, added_date FROM products")
        columns = [column[0] for column in cursor.description]
        data = cursor.fetchall()

        if not data:
            await message.answer("📭 Склад пуст! Нет данных для экспорта.",
                                 reply_markup=get_main_keyboard(message.from_user.id))
            return

        output = BytesIO()
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Склад"
        sheet.append(columns)

        for row in data:
            sheet.append(row)
            if row[2] < 10:
                pass

        workbook.save(output)
        output.seek(0)

        file_data = output.getvalue()
        filename = f"склад_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.xlsx"

        excel_file = BufferedInputFile(
            file=file_data,
            filename=filename
        )

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
        if 'output' in locals():
            output.close()


# ===== ОТЧЕТ ПО СМЕНЕ =====
@dp.message(F.text == "📝 Отчёт по смене")
@access_required
async def shift_report_menu(message: types.Message):
    await message.answer(
        "📝 Управление отчётами по смене\n"
        "Выберите действие:",
        reply_markup=get_report_keyboard()
    )


@dp.message(F.text == "📋 Создать отчёт")
@access_required
async def create_report_start(message: types.Message):
    user_id = message.from_user.id
    today = datetime.now().strftime('%Y-%m-%d')

    cursor.execute("SELECT id FROM shift_reports WHERE user_id = ? AND report_date = ?", (user_id, today))
    if cursor.fetchone():
        await message.answer("⚠️ Отчёт за сегодня уже существует! Используйте 'Обновить отчёт'.")
        return

    user_states[user_id] = "report_date"
    user_data[user_id] = {
        'report': {
            'report_date': today,
            'fields': ['total', 'cash', 'card', 'bar', 'hookah', 'expenses', 'balance'],
            'current_field': 0,
            'labels': [
                "общую сумму выручки",
                "сумму наличных",
                "сумму безналичных",
                "выручку по бару",
                "выручку по кальянам",
                "сумму расходов",
                "остаток в кассе"
            ]
        }
    }

    await message.answer(
        f"📅 Создание отчёта за {today}\n"
        f"Введите {user_data[user_id]['report']['labels'][0]}:",
        reply_markup=get_cancel_keyboard()
    )


@dp.message(F.text == "🔄 Обновить отчёт")
@access_required
async def update_report_start(message: types.Message):
    user_id = message.from_user.id
    today = datetime.now().strftime('%Y-%m-%d')

    cursor.execute(
        "SELECT total, cash, card, bar, hookah, expenses, balance "
        "FROM shift_reports WHERE user_id = ? AND report_date = ?",
        (user_id, today)
    )
    report = cursor.fetchone()

    if not report:
        await message.answer("ℹ️ Отчёт за сегодня ещё не создан. Используйте 'Создать отчёт'.")
        return

    user_states[user_id] = "update_report"
    user_data[user_id] = {
        'report': {
            'report_date': today,
            'fields': ['total', 'cash', 'card', 'bar', 'hookah', 'expenses', 'balance'],
            'current_field': 0,
            'values': list(report),
            'labels': [
                "общую сумму выручки",
                "сумму наличных",
                "сумму безналичных",
                "выручку по бару",
                "выручку по кальянам",
                "сумму расходов",
                "остаток в кассе"
            ]
        }
    }

    await message.answer(
        f"🔄 Обновление отчёта за {today}\n"
        f"Текущее значение {user_data[user_id]['report']['labels'][0]}: "
        f"{user_data[user_id]['report']['values'][0]}\n"
        f"Введите новое значение:",
        reply_markup=get_cancel_keyboard()
    )


@dp.message(F.text, lambda message: user_states.get(message.from_user.id) in ["report_date", "update_report"])
async def process_report_data(message: types.Message):
    if message.text == "❌ Отмена":
        user_id = message.from_user.id
        user_states[user_id] = None
        if 'report' in user_data[user_id]:
            del user_data[user_id]['report']
        await message.answer("❌ Создание отчета отменено", reply_markup=get_report_keyboard())
        return

    user_id = message.from_user.id
    state = user_states[user_id]
    report_data = user_data[user_id]['report']
    current_field = report_data['current_field']

    try:
        value = float(message.text.replace(',', '.'))
        if value < 0:
            raise ValueError("Отрицательное значение")
    except:
        await message.answer("❌ Ошибка! Введите корректное положительное число.", reply_markup=get_cancel_keyboard())
        return

    if state == "report_date":
        report_data[report_data['fields'][current_field]] = value
    else:
        report_data['values'][current_field] = value

    report_data['current_field'] += 1

    if report_data['current_field'] < len(report_data['fields']):
        current_index = report_data['current_field']
        field_label = report_data['labels'][current_index]
        await message.answer(f"Введите {field_label}:", reply_markup=get_cancel_keyboard())
        return

    try:
        if state == "report_date":
            cursor.execute(
                "INSERT INTO shift_reports "
                "(user_id, report_date, total, cash, card, bar, hookah, expenses, balance) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, report_data['report_date'],
                 report_data['total'], report_data['cash'], report_data['card'],
                 report_data['bar'], report_data['hookah'], report_data['expenses'],
                 report_data['balance'])
            )
            action = "создан"
        else:
            cursor.execute(
                "UPDATE shift_reports SET "
                "total = ?, cash = ?, card = ?, bar = ?, "
                "hookah = ?, expenses = ?, balance = ? "
                "WHERE user_id = ? AND report_date = ?",
                (report_data['values'][0], report_data['values'][1],
                 report_data['values'][2], report_data['values'][3],
                 report_data['values'][4], report_data['values'][5],
                 report_data['values'][6], user_id, report_data['report_date'])
            )
            action = "обновлен"

        conn.commit()

        if state == "report_date":
            report_values = [
                report_data['total'], report_data['cash'], report_data['card'],
                report_data['bar'], report_data['hookah'], report_data['expenses'],
                report_data['balance']
            ]
        else:
            report_values = report_data['values']

        report_text = (
            f"📝 Отчёт по смене {report_data['report_date']} {action}:\n\n"
            f"• Общая сумма: {report_values[0]} ₽\n"
            f"• Наличные: {report_values[1]} ₽\n"
            f"• Безналичные: {report_values[2]} ₽\n"
            f"• Бар: {report_values[3]} ₽\n"
            f"• Кальян: {report_values[4]} ₽\n"
            f"• Расходы: {report_values[5]} ₽\n"
            f"• Остаток: {report_values[6]} ₽\n\n"
            f"💸 Чистая прибыль: {report_values[0] - report_values[5]} ₽"
        )

        await message.answer(report_text, reply_markup=get_report_keyboard())
        await log_action(user_id, f"Отчёт {action}", f"Дата: {report_data['report_date']}")

    except Exception as e:
        logger.error(f"Ошибка сохранения отчёта: {e}")
        await message.answer("❌ Ошибка сохранения отчёта!", reply_markup=get_report_keyboard())

    finally:
        user_states[user_id] = None
        if 'report' in user_data[user_id]:
            del user_data[user_id]['report']


@dp.message(F.text == "📅 История отчётов")
@access_required
async def report_history(message: types.Message):
    user_id = message.from_user.id

    try:
        cursor.execute(
            "SELECT report_date, total, cash, card, bar, hookah, expenses, balance "
            "FROM shift_reports WHERE user_id = ? ORDER BY report_date DESC LIMIT 10",
            (user_id,)
        )
        reports = cursor.fetchall()

        if not reports:
            await message.answer("📭 У вас ещё нет сохранённых отчётов.")
            return

        response = "📅 Последние 10 отчётов:\n\n"
        for report in reports:
            response += (
                f"📅 {report[0]}\n"
                f"├ Общая сумма: {report[1]} ₽\n"
                f"├ Наличные: {report[2]} ₽\n"
                f"├ Безнал: {report[3]} ₽\n"
                f"├ Бар: {report[4]} ₽\n"
                f"├ Кальян: {report[5]} ₽\n"
                f"├ Расходы: {report[6]} ₽\n"
                f"└ Остаток: {report[7]} ₽\n\n"
            )

        await message.answer(response, reply_markup=get_report_keyboard())

    except Exception as e:
        logger.error(f"Ошибка получения истории отчётов: {e}")
        await message.answer("❌ Ошибка получения истории отчётов!", reply_markup=get_report_keyboard())


# ===== ОБРАБОТЧИК ОТМЕНЫ =====
@dp.message(F.text == "❌ Отмена")
@access_required
async def cancel_action(message: types.Message):
    user_id = message.from_user.id
    state = user_states.get(user_id)

    if state:
        # Определяем, в каком состоянии находится пользователь
        if state.startswith(("adding_", "searching", "editing_")):
            # Для операций со складом
            user_states[user_id] = None
            if user_id in user_data:
                user_data[user_id] = {}
            await message.answer("❌ Действие отменено", reply_markup=get_warehouse_keyboard())
        elif state in ["report_date", "update_report"]:
            # Для операций с отчетами
            user_states[user_id] = None
            if user_id in user_data and 'report' in user_data[user_id]:
                del user_data[user_id]['report']
            await message.answer("❌ Действие отменено", reply_markup=get_report_keyboard())
        elif state.endswith(("_user")):
            # Для операций управления пользователями
            user_states[user_id] = None
            await message.answer("❌ Действие отменено", reply_markup=get_user_management_keyboard())
    else:
        await message.answer("❌ Нет активных действий для отмены", reply_markup=get_main_keyboard(user_id))


# ===== ОБРАБОТЧИК КНОПКИ "НАЗАД" =====
@dp.message(F.text == "🔙 Назад")
async def back_handler(message: types.Message):
    user_id = message.from_user.id

    # Если пользователь в процессе редактирования товара
    if user_states.get(user_id) in ["editing_name", "editing_quantity", "editing_category"]:
        user_states[user_id] = None
        await message.answer("❌ Изменение товара отменено", reply_markup=get_warehouse_keyboard())
        return

    # Если пользователь в меню выбора действия для товара
    if user_data.get(user_id) and "edit_id" in user_data[user_id]:
        # Возвращаем к списку товаров для редактирования
        await edit_product_start(message)
        return

    # По умолчанию возвращаем в главное меню
    await message.answer("Главное меню:", reply_markup=get_main_keyboard(user_id))


# ===== ОБРАБОТЧИК КНОПКИ "НАЗАД В ГЛАВНОЕ МЕНЮ" =====
@dp.message(F.text == "🔙 Назад в главное меню")
async def back_to_main_menu(message: types.Message):
    await message.answer("Главное меню:", reply_markup=get_main_keyboard(message.from_user.id))


# ===== ОБРАБОТЧИКИ ДЛЯ ГРУПП И НЕИЗВЕСТНЫХ КОМАНД =====
@dp.message(F.chat.type.in_({"group", "supergroup"}))
async def handle_group_messages(message: types.Message):
    pass


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
    # Логирование информации о запуске
    logger.info("=" * 50)
    logger.info(f"🤖 ЗАПУСК СИСТЕМЫ SoraEcoSystemBot")
    logger.info(f"⏰ Время запуска: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"🔑 ID главного администратора: {MAIN_ADMIN_ID}")

    # Проверка и создание главного администратора
    if not is_registered(MAIN_ADMIN_ID):
        cursor.execute(
            "INSERT INTO users (user_id, username, first_name, is_admin) VALUES (?, ?, ?, ?)",
            (MAIN_ADMIN_ID, "sora_admin", "Sora Admin", 1)
        )
        conn.commit()
        logger.info("✅ Главный администратор зарегистрирован")

    # Статистика системы
    try:
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM products")
        product_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM action_logs")
        log_count = cursor.fetchone()[0]

        logger.info(f"👥 Пользователей в системе: {user_count}")
        logger.info(f"📦 Товаров на складе: {product_count}")
        logger.info(f"📝 Лог-записей действий: {log_count}")
        logger.info("=" * 50)
    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {e}")

    # Запуск бота
    logger.info("🟢 Бот запущен и готов к работе")
    try:
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logger.info("⏹️ Получен сигнал остановки (Ctrl+C)")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при работе бота: {e}")
    finally:
        # Логирование завершения работы
        logger.info("=" * 50)
        logger.info(f"🛑 ЗАВЕРШЕНИЕ РАБОТЫ SoraEcoSystemBot")
        logger.info(f"⏰ Время остановки: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        try:
            cursor.execute("SELECT COUNT(*) FROM action_logs WHERE timestamp > datetime('now', '-1 day')")
            actions_24h = cursor.fetchone()[0]
            logger.info(f"⚡ Активность за 24 часа: {actions_24h} действий")
        except:
            pass

        logger.info("📦 Закрытие соединения с базой данных...")
        conn.close()
        logger.info("✅ Соединение с базой данных закрыто")
        logger.info("=" * 50)
        logger.info("👋 Работа бота завершена")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⏹️ Программа прервана пользователем")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
    finally:
        logger.info("👋 Программа завершена")