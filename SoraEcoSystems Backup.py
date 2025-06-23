import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, FSInputFile, ReplyKeyboardRemove, InlineKeyboardMarkup, \
    InlineKeyboardButton
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
import logging
import sys

# Загрузка токена из переменных окружения
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

# Проверка токена
if not TOKEN:
    logging.error("Токен бота не найден! Убедитесь, что переменная BOT_TOKEN установлена в .env файле.")
    sys.exit(1)

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
bot = Bot(token=TOKEN)
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
                   is_approved
                   BOOLEAN
                   DEFAULT
                   0,
                   added_date
                   TIMESTAMP
                   DEFAULT
                   CURRENT_TIMESTAMP,
                   last_action
                   TIMESTAMP
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

# ОБНОВЛЕННАЯ ТАБЛИЦА ОТЧЕТОВ
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
                   hookah_count
                   INTEGER
                   NOT
                   NULL,
                   expenses
                   REAL
                   NOT
                   NULL,
                   initial_cash
                   REAL
                   DEFAULT
                   4000,
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

# НОВАЯ ТАБЛИЦА ДЛЯ УПРАВЛЕНИЯ УВЕДОМЛЕНИЯМИ
cursor.execute('''
               CREATE TABLE IF NOT EXISTS notification_settings
               (
                   id
                   INTEGER
                   PRIMARY
                   KEY
                   AUTOINCREMENT,
                   notification_type
                   TEXT
                   NOT
                   NULL
                   UNIQUE,
                   chat_id
                   TEXT
                   NOT
                   NULL
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


# Функция для проверки одобрения пользователя
def is_approved(user_id):
    if user_id == MAIN_ADMIN_ID:
        return True
    try:
        cursor.execute("SELECT is_approved FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        return result and result[0] == 1
    except Exception as e:
        logger.error(f"Ошибка проверки одобрения для {user_id}: {e}")
        return False


# Функция для регистрации пользователя
def register_user(user_id, username, first_name):
    try:
        cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        if not cursor.fetchone():
            # Для главного администратора всегда одобрен и админ
            if user_id == MAIN_ADMIN_ID:
                is_admin_val = 1
                is_approved_val = 1
            else:
                is_admin_val = 0
                is_approved_val = 0  # По умолчанию не одобрен

            cursor.execute(
                "INSERT INTO users (user_id, username, first_name, is_admin, is_approved) VALUES (?, ?, ?, ?, ?)",
                (user_id, username, first_name, is_admin_val, is_approved_val)
            )
            conn.commit()
            logger.info(
                f"Зарегистрирован новый пользователь: ID={user_id}, Имя={first_name}, Админ={is_admin_val}, Одобрен={is_approved_val}")
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


# Функция для получения chat_id для уведомлений
def get_notification_chat(notification_type: str) -> str:
    try:
        cursor.execute(
            "SELECT chat_id FROM notification_settings WHERE notification_type = ?",
            (notification_type,)
        )
        result = cursor.fetchone()
        return result[0] if result else None
    except Exception as e:
        logger.error(f"Ошибка получения чата для {notification_type}: {e}")
        return None


# Функция для логирования действий
async def log_action(user_id, action, details=""):
    try:
        cursor.execute(
            "INSERT INTO action_logs (user_id, action, details) VALUES (?, ?, ?)",
            (user_id, action, details)
        )
        conn.commit()
        logger.info(f"Действие пользователя {user_id}: {action} - {details}")

        # Обновляем время последнего действия пользователя
        update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute(
            "UPDATE users SET last_action = ? WHERE user_id = ?",
            (update_time, user_id)
        )
        conn.commit()

        # Отправляем уведомление в настроенный чат или главному администратору
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

            # Получаем чат для уведомлений из настроек
            action_chat_id = get_notification_chat("actions") or MAIN_ADMIN_ID
            try:
                await bot.send_message(action_chat_id, notification)
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления: {e}")
    except Exception as e:
        logger.error(f"Ошибка логирования действия: {e}")


# ===== ФУНКЦИЯ АВТОМАТИЧЕСКОЙ РЕГИСТРАЦИИ =====
async def register_if_needed(message: types.Message) -> bool:
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name

    # Если пользователь не зарегистрирован
    if not is_registered(user_id):
        # Регистрируем нового пользователя
        if register_user(user_id, username, first_name):
            await message.answer(
                "✅ Вы успешно зарегистрированы!\n"
                "⏳ Ожидайте подтверждения доступа администратором."
            )
            logger.info(f"Зарегистрирован новый пользователь: {user_id}")

            # Уведомляем администратора
            admin_notification = (
                f"👤 Новый пользователь!\n"
                f"🆔 ID: {user_id}\n"
                f"👨‍💼 Имя: {first_name}\n"
                f"📎 Username: @{username}\n\n"
                f"Для одобрения доступа используйте админ-панель."
            )
            try:
                await bot.send_message(MAIN_ADMIN_ID, admin_notification)
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления админу: {e}")
            return True
        else:
            await message.answer("❌ Ошибка регистрации. Обратитесь к администратору.")
            return False
    return True


# ===== ОБНОВЛЕННЫЕ MIDDLEWARE ДЛЯ ПРОВЕРКИ ДОСТУПА =====
def access_required(func):
    async def wrapper(message: types.Message):
        user_id = message.from_user.id

        # Автоматическая регистрация при необходимости
        if not (await register_if_needed(message)):
            return

        # Проверка бана
        if is_banned(user_id):
            await message.answer("❌ Ваш доступ к боту заблокирован.")
            return

        # Проверка одобрения (главный администратор всегда одобрен)
        if not is_approved(user_id) and user_id != MAIN_ADMIN_ID:
            await message.answer("❌ Ваш доступ к боту еще не подтвержден администратором. Ожидайте одобрения.")
            return

        return await func(message)

    return wrapper


def admin_required(func):
    async def wrapper(message: types.Message):
        user_id = message.from_user.id

        # Автоматическая регистрация при необходимости
        if not (await register_if_needed(message)):
            return

        if is_banned(user_id):
            await message.answer("❌ Ваш доступ к боту заблокирован.")
            return

        if not is_approved(user_id) and user_id != MAIN_ADMIN_ID:
            await message.answer("❌ Ваш доступ к боту еще не подтвержден администратором.")
            return

        if not is_admin(user_id):
            await message.answer("❌ У вас нет прав администратора для выполнения этого действия.")
            return
        return await func(message)

    return wrapper


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
            [KeyboardButton(text="🔒 Управление доступом")],
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="📋 Логи действий")],
            [KeyboardButton(text="🔔 Управление уведомлениями")],  # Новая кнопка
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


def get_access_management_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👥 Список всех пользователей")],
            [KeyboardButton(text="✅ Одобрить доступ"), KeyboardButton(text="🚫 Запретить доступ")],
            [KeyboardButton(text="👀 Показать неодобренных")],
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


# ===== КЛАВИАТУРА ДЛЯ УПРАВЛЕНИЯ УВЕДОМЛЕНИЯМИ =====
def get_notification_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👁 Просмотреть настройки")],
            [KeyboardButton(text="✏️ Установить текущий чат для отчетов")],
            [KeyboardButton(text="✏️ Установить текущий чат для действий")],
            [KeyboardButton(text="❓ Как получить ID чата?")],
            [KeyboardButton(text="🔙 Назад в админ-панель")]
        ],
        resize_keyboard=True
    )


# ===== КЛАВИАТУРА ОТМЕНЫ =====
def get_cancel_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True
    )


# ===== КЛАВИАТУРА ДЛЯ ПРОПУСКА ПРИ ОБНОВЛЕНИИ ОТЧЕТА =====
def get_skip_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⏭ Пропустить")],
            [KeyboardButton(text="❌ Отмена")]
        ],
        resize_keyboard=True
    )


# ===== КОМАНДА /start =====
@dp.message(Command("start"))
@access_required
async def start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name

    # Автоматическая регистрация главного администратора
    if user_id == MAIN_ADMIN_ID and not is_registered(user_id):
        cursor.execute(
            "INSERT INTO users (user_id, username, first_name, is_admin, is_approved) VALUES (?, ?, ?, ?, ?)",
            (user_id, username, first_name, 1, 1)
        )
        conn.commit()
        logger.info(f"Главный администратор зарегистрирован: {user_id}")

    # Проверяем, заблокирован ли пользователь
    if is_banned(user_id):
        await message.answer("❌ Ваш доступ к боту заблокирован администратором.")
        return

    # Проверяем одобрен ли пользователь
    if not is_approved(user_id) and user_id != MAIN_ADMIN_ID:
        await message.answer(
            "❌ Ваш доступ к боту еще не подтвержден.\n"
            "⏳ Ожидайте одобрения администратором."
        )
        return

    user_states[user_id] = None
    user_data[user_id] = {}

    welcome_text = "🛒 Добро пожаловать в складской бот!\n"
    await message.answer(welcome_text, reply_markup=get_main_keyboard(user_id))
    await log_action(user_id, "Запуск бота", "Пользователь вошел в систему")


# ===== АДМИН-ПАНЕЛЬ =====
@dp.message(F.text == "👑 Админ-панель")
@admin_required
async def admin_panel(message: types.Message):
    await message.answer(
        "👑 Панель администратора\n"
        "Выберите действие:",
        reply_markup=get_admin_keyboard()
    )


@dp.message(F.text == "🔔 Управление уведомлениями")
@admin_required
async def notification_management(message: types.Message):
    await message.answer(
        "🔔 Управление уведомлениями\n"
        "Выберите действие:",
        reply_markup=get_notification_keyboard()
    )


@dp.message(F.text == "👁 Просмотреть настройки")
@admin_required
async def view_notification_settings(message: types.Message):
    try:
        cursor.execute("SELECT * FROM notification_settings")
        settings = cursor.fetchall()

        response = "🔔 Текущие настройки уведомлений:\n\n"

        if not settings:
            response += "Настроек пока нет."
        else:
            for setting in settings:
                response += f"• Тип: {setting[1]}\n"
                response += f"  Чат ID: {setting[2]}\n\n"

        await message.answer(response)

    except Exception as e:
        logger.error(f"Ошибка при получении настроек уведомлений: {e}")
        await message.answer("❌ Ошибка при получении настроек уведомлений")


@dp.message(F.text == "✏️ Установить текущий чат для отчетов")
@admin_required
async def set_report_chat_current(message: types.Message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    # Проверяем, что бот администратор в этом чате (для групп)
    if message.chat.type != "private":
        try:
            chat_member = await bot.get_chat_member(chat_id, bot.id)
            if not chat_member.status in ['administrator', 'creator']:
                await message.answer(
                    "❌ Бот должен быть администратором в этом чате!\n"
                    "Пожалуйста, назначьте бота администратором и повторите попытку."
                )
                return
        except Exception as e:
            logger.error(f"Ошибка проверки прав бота: {e}")
            await message.answer("❌ Не удалось проверить права бота в этом чате.")
            return

    try:
        # Сохраняем или обновляем настройку
        cursor.execute(
            "INSERT OR REPLACE INTO notification_settings (notification_type, chat_id) VALUES (?, ?)",
            ("reports", str(chat_id))
        )
        conn.commit()

        await message.answer(
            f"✅ Чат для отчетов успешно установлен!\n"
            f"ID чата: {chat_id}\n"
            f"Все отчеты будут отправляться сюда.",
            reply_markup=get_notification_keyboard()
        )

        await log_action(user_id, "Настройка уведомлений",
                         f"Установлен чат для отчетов: {chat_id}")

    except Exception as e:
        logger.error(f"Ошибка сохранения настроек уведомлений: {e}")
        await message.answer("❌ Ошибка сохранения настроек. Попробуйте позже.",
                             reply_markup=get_notification_keyboard())


@dp.message(F.text == "✏️ Установить текущий чат для действий")
@admin_required
async def set_action_chat_current(message: types.Message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    # Проверяем, что бот администратор в этом чате (для групп)
    if message.chat.type != "private":
        try:
            chat_member = await bot.get_chat_member(chat_id, bot.id)
            if not chat_member.status in ['administrator', 'creator']:
                await message.answer(
                    "❌ Бот должен быть администратором в этом чате!\n"
                    "Пожалуйста, назначьте бота администратором и повторите попытку."
                )
                return
        except Exception as e:
            logger.error(f"Ошибка проверки прав бота: {e}")
            await message.answer("❌ Не удалось проверить права бота в этом чате.")
            return

    try:
        # Сохраняем или обновляем настройку
        cursor.execute(
            "INSERT OR REPLACE INTO notification_settings (notification_type, chat_id) VALUES (?, ?)",
            ("actions", str(chat_id))
        )
        conn.commit()

        await message.answer(
            f"✅ Чат для логов действий успешно установлен!\n"
            f"ID чата: {chat_id}\n"
            f"Все логи действий будут отправляться сюда.",
            reply_markup=get_notification_keyboard()
        )

        await log_action(user_id, "Настройка уведомлений",
                         f"Установлен чат для действий: {chat_id}")

    except Exception as e:
        logger.error(f"Ошибка сохранения настроек уведомлений: {e}")
        await message.answer("❌ Ошибка сохранения настроек. Попробуйте позже.",
                             reply_markup=get_notification_keyboard())


@dp.message(F.text == "❓ Как получить ID чата?")
@admin_required
async def how_to_get_chat_id(message: types.Message):
    help_text = (
        "ℹ️ Как установить чат для уведомлений:\n\n"
        "1. Перейдите в нужный чат (группу или канал)\n"
        "2. Убедитесь, что бот добавлен в этот чат и имеет права администратора\n"
        "3. В этом чате вызовите команду /id\n"
        "4. Бот покажет ID этого чата\n\n"
        "Для установки текущего чата:\n"
        "- В меню уведомлений выберите:\n"
        "  • '✏️ Установить текущий чат для отчетов' - для отчетов\n"
        "  • '✏️ Установить текущий чат для действий' - для логов действий\n\n"
        "Для установки чата из личных сообщений просто используйте соответствующие кнопки."
    )
    await message.answer(help_text)


# Команда для получения ID чата
@dp.message(Command("id"))
async def get_chat_id(message: types.Message):
    chat_id = message.chat.id
    chat_type = message.chat.type

    response = (
        f"ℹ️ Информация о чате:\n"
        f"Тип: {'личные сообщения' if chat_type == 'private' else 'группа' if chat_type == 'group' else 'супергруппа' if chat_type == 'supergroup' else 'канал'}\n"
        f"ID чата: `{chat_id}`\n\n"
        "Этот ID можно использовать для настройки уведомлений в админ-панели."
    )

    await message.answer(response, parse_mode="Markdown")


@dp.message(F.text == "🔒 Управление доступом")
@admin_required
async def access_management(message: types.Message):
    await message.answer(
        "🔒 Управление доступом пользователей\n"
        "Выберите действие:",
        reply_markup=get_access_management_keyboard()
    )


@dp.message(F.text == "👀 Показать неодобренных")
@admin_required
async def show_unapproved_users(message: types.Message):
    try:
        cursor.execute("""
                       SELECT user_id, username, first_name, added_date
                       FROM users
                       WHERE is_approved = 0
                         AND is_banned = 0
                       ORDER BY added_date DESC
                       """)
        users = cursor.fetchall()

        if not users:
            await message.answer("✅ Все пользователи одобрены или заблокированы.")
            return

        response = "👥 Пользователи, ожидающие одобрения:\n\n"
        for user in users:
            user_id = user[0]
            username = user[1] or "без username"
            first_name = user[2] or "Без имени"
            added_date = user[3]

            response += (
                f"🆔 ID: {user_id}\n"
                f"👤 Имя: {first_name}\n"
                f"📎 @{username}\n"
                f"📅 Зарегистрирован: {added_date}\n\n"
            )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[])
        for user in users:
            user_id = user[0]
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(
                    text=f"✅ Одобрить {user_id}",
                    callback_data=f"approve_{user_id}"
                )
            ])

        if len(response) > 4000:
            await message.answer("Список слишком большой, используйте кнопки для управления:")
            await message.answer("Выберите пользователя для одобрения:", reply_markup=keyboard)
        else:
            await message.answer(response, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Ошибка при получении списка неодобренных пользователей: {e}")
        await message.answer("❌ Ошибка при получении списка пользователей.")


@dp.message(F.text == "✅ Одобрить доступ")
@admin_required
async def approve_access_start(message: types.Message):
    try:
        cursor.execute("""
                       SELECT user_id, username, first_name, added_date
                       FROM users
                       WHERE is_approved = 0
                         AND is_banned = 0
                       ORDER BY added_date DESC
                       """)
        users = cursor.fetchall()

        if not users:
            await message.answer("✅ Все пользователи уже одобрены.")
            return

        keyboard = InlineKeyboardMarkup(inline_keyboard=[])
        for user in users:
            user_id = user[0]
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(
                    text=f"✅ Одобрить {user_id}",
                    callback_data=f"approve_{user_id}"
                )
            ])

        await message.answer(
            "👥 Выберите пользователя для одобрения доступа:",
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Ошибка при получении списка неодобренных пользователей: {e}")
        await message.answer("❌ Ошибка при получении списка пользователей.")


@dp.message(F.text == "🚫 Запретить доступ")
@admin_required
async def disapprove_access_start(message: types.Message):
    try:
        cursor.execute("""
                       SELECT user_id, username, first_name, added_date
                       FROM users
                       WHERE is_approved = 1
                         AND is_banned = 0
                       ORDER BY added_date DESC
                       """)
        users = cursor.fetchall()

        if not users:
            await message.answer("ℹ️ Нет одобренных пользователей для запрета доступа.")
            return

        keyboard = InlineKeyboardMarkup(inline_keyboard=[])
        for user in users:
            user_id = user[0]
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(
                    text=f"🚫 Запретить {user_id}",
                    callback_data=f"disapprove_{user_id}"
                )
            ])

        await message.answer(
            "👥 Выберите пользователя для запрета доступа:",
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Ошибка при получении списка одобренных пользователей: {e}")
        await message.answer("❌ Ошибка при получении списка пользователей.")


# Обработчик кнопки одобрения пользователя
@dp.callback_query(F.data.startswith("approve_"))
async def handle_approve_user(callback: types.CallbackQuery):
    try:
        user_id = int(callback.data.split("_")[1])

        # Обновляем статус пользователя
        cursor.execute("UPDATE users SET is_approved = 1 WHERE user_id = ?", (user_id,))
        conn.commit()

        # Получаем информацию о пользователе
        cursor.execute("SELECT first_name, username FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        first_name = user[0] if user and user[0] else "Пользователь"
        username = user[1] if user and user[1] else "без username"

        # Уведомляем администратора
        await callback.message.answer(
            f"✅ Пользователь одобрен!\n"
            f"👤 {first_name} (@{username})\n"
            f"🆔 ID: {user_id}"
        )

        # Уведомляем пользователя
        try:
            await bot.send_message(
                user_id,
                "🎉 Ваш доступ к боту подтвержден администратором!\n"
                "Теперь вы можете пользоваться всеми функциями."
            )
        except Exception as e:
            logger.error(f"Не удалось уведомить пользователя {user_id}: {e}")

        # Удаляем сообщение с кнопкой
        await callback.message.delete()
        await callback.answer()

        await log_action(callback.from_user.id, "Одобрение пользователя", f"ID: {user_id}")

    except Exception as e:
        logger.error(f"Ошибка при одобрении пользователя: {e}")
        await callback.answer("❌ Ошибка при одобрении пользователя")


# Обработчик кнопки запрета доступа пользователя
@dp.callback_query(F.data.startswith("disapprove_"))
async def handle_disapprove_user(callback: types.CallbackQuery):
    try:
        user_id = int(callback.data.split("_")[1])

        # Обновляем статус пользователя
        cursor.execute("UPDATE users SET is_approved = 0 WHERE user_id = ?", (user_id,))
        conn.commit()

        # Получаем информацию о пользователе
        cursor.execute("SELECT first_name, username FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        first_name = user[0] if user and user[0] else "Пользователь"
        username = user[1] if user and user[1] else "без username"

        # Уведомляем администратора
        await callback.message.answer(
            f"🚫 Доступ пользователя запрещен!\n"
            f"👤 {first_name} (@{username})\n"
            f"🆔 ID: {user_id}"
        )

        # Уведомляем пользователя
        try:
            await bot.send_message(
                user_id,
                "🚫 Ваш доступ к боту был отозван администратором.\n"
                "Для выяснения причин обратитесь к администратору."
            )
        except Exception as e:
            logger.error(f"Не удалось уведомить пользователя {user_id}: {e}")

        # Удаляем сообщение с кнопкой
        await callback.message.delete()
        await callback.answer()

        await log_action(callback.from_user.id, "Запрет доступа", f"ID: {user_id}")

    except Exception as e:
        logger.error(f"Ошибка при запрете доступа: {e}")
        await callback.answer("❌ Ошибка при запрете доступа")


@dp.message(F.text == "👥 Список всех пользователей")
@admin_required
async def list_all_users(message: types.Message):
    try:
        cursor.execute("""
                       SELECT user_id, username, first_name, is_admin, is_banned, is_approved, added_date
                       FROM users
                       ORDER BY added_date DESC
                       """)
        users = cursor.fetchall()

        if not users:
            await message.answer("👥 Пользователей нет в базе данных.")
            return

        keyboard = InlineKeyboardMarkup(inline_keyboard=[])
        for user in users:
            user_id = user[0]
            username = user[1] or "без username"
            first_name = user[2] or "Без имени"

            status = ""
            if user[3]: status += "👑"  # is_admin
            if user[4]: status += "🚫"  # is_banned
            if user[5]:
                status += "✅"  # is_approved
            else:
                status += "⏳"  # не одобрен

            button_text = f"{status} {first_name} (@{username})"

            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text=button_text, callback_data=f"user_{user_id}")
            ])

        await message.answer(
            "👥 Список всех пользователей. Выберите пользователя:",
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Ошибка при получении списка пользователей: {e}")
        await message.answer("❌ Ошибка при получении списка пользователей.")


# Обработчик выбора пользователя из списка
@dp.callback_query(F.data.startswith("user_"))
async def handle_user_selected(callback: types.CallbackQuery):
    try:
        user_id = int(callback.data.split("_")[1])

        cursor.execute("""
                       SELECT user_id,
                              username,
                              first_name,
                              is_admin,
                              is_banned,
                              is_approved,
                              added_date,
                              last_action
                       FROM users
                       WHERE user_id = ?
                       """, (user_id,))
        user = cursor.fetchone()

        if not user:
            await callback.answer("❌ Пользователь не найден")
            return

        user_id, username, first_name, is_admin, is_banned, is_approved, added_date, last_action = user

        status = []
        if is_admin:
            status.append("👑 Администратор")
        else:
            status.append("👤 Обычный пользователь")

        if is_banned:
            status.append("🚫 Заблокирован")

        if is_approved:
            status.append("✅ Доступ разрешен")
        else:
            status.append("⏳ Ожидает одобрения")

        last_action = last_action or "никогда"

        response = (
            f"👤 Информация о пользователе:\n"
            f"🆔 ID: {user_id}\n"
            f"👨‍💼 Имя: {first_name or 'не указано'}\n"
            f"📎 Username: @{username or 'не указан'}\n"
            f"📌 Статус: {'; '.join(status)}\n"
            f"📅 Дата регистрации: {added_date}\n"
            f"⏱ Последнее действие: {last_action}"
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[])

        if not is_approved:
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text="✅ Одобрить доступ", callback_data=f"approve_{user_id}")
            ])
        else:
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text="🚫 Запретить доступ", callback_data=f"disapprove_{user_id}")
            ])

        if not is_admin and not is_banned:
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text="🚫 Заблокировать", callback_data=f"ban_{user_id}")
            ])
        elif is_banned:
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text="✅ Разблокировать", callback_data=f"unban_{user_id}")
            ])

        if not is_admin:
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text="⚡ Сделать админом", callback_data=f"promote_{user_id}")
            ])
        else:
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text="❌ Снять админство", callback_data=f"demote_{user_id}")
            ])

        await callback.message.answer(response, reply_markup=keyboard)
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при обработке выбора пользователя: {e}")
        await callback.answer("❌ Ошибка при получении информации")


@dp.callback_query(F.data.startswith("promote_"))
async def promote_user_callback(callback: types.CallbackQuery):
    try:
        target_user_id = int(callback.data.split("_")[1])
        admin_id = callback.from_user.id

        if target_user_id == MAIN_ADMIN_ID:
            await callback.answer("❌ Нельзя изменить статус главного администратора")
            return

        cursor.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (target_user_id,))
        conn.commit()

        cursor.execute("SELECT first_name, username FROM users WHERE user_id = ?", (target_user_id,))
        user = cursor.fetchone()
        first_name = user[0] if user and user[0] else "Пользователь"
        username = user[1] if user and user[1] else "без username"

        await callback.message.answer(
            f"⚡ Пользователь назначен администратором!\n"
            f"👑 {first_name} (@{username})\n"
            f"🆔 ID: {target_user_id}"
        )

        try:
            await bot.send_message(
                target_user_id,
                "🎉 Вам предоставлены права администратора!\n"
                "Теперь вы можете управлять ботом."
            )
        except Exception as e:
            logger.error(f"Не удалось уведомить пользователя {target_user_id}: {e}")

        await callback.answer()
        await log_action(admin_id, "Назначение администратора", f"ID: {target_user_id}")

    except Exception as e:
        logger.error(f"Ошибка при назначении администратора: {e}")
        await callback.answer("❌ Ошибка при назначении администратора")


@dp.callback_query(F.data.startswith("demote_"))
async def demote_user_callback(callback: types.CallbackQuery):
    try:
        target_user_id = int(callback.data.split("_")[1])
        admin_id = callback.from_user.id

        if target_user_id == MAIN_ADMIN_ID:
            await callback.answer("❌ Нельзя изменить статус главного администратора")
            return

        cursor.execute("UPDATE users SET is_admin = 0 WHERE user_id = ?", (target_user_id,))
        conn.commit()

        cursor.execute("SELECT first_name, username FROM users WHERE user_id = ?", (target_user_id,))
        user = cursor.fetchone()
        first_name = user[0] if user and user[0] else "Пользователь"
        username = user[1] if user and user[1] else "без username"

        await callback.message.answer(
            f"❌ Админские права отозваны!\n"
            f"👤 {first_name} (@{username})\n"
            f"🆔 ID: {target_user_id}"
        )

        try:
            await bot.send_message(
                target_user_id,
                "❌ Ваши права администратора были отозваны."
            )
        except Exception as e:
            logger.error(f"Не удалось уведомить пользователя {target_user_id}: {e}")

        await callback.answer()
        await log_action(admin_id, "Снятие прав администратора", f"ID: {target_user_id}")

    except Exception as e:
        logger.error(f"Ошибка при снятии прав администратора: {e}")
        await callback.answer("❌ Ошибка при снятии прав администратора")


@dp.callback_query(F.data.startswith("ban_"))
async def ban_user_callback(callback: types.CallbackQuery):
    try:
        target_user_id = int(callback.data.split("_")[1])
        admin_id = callback.from_user.id

        if target_user_id == MAIN_ADMIN_ID:
            await callback.answer("❌ Нельзя заблокировать главного администратора")
            return

        cursor.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (target_user_id,))
        conn.commit()

        cursor.execute("SELECT first_name, username FROM users WHERE user_id = ?", (target_user_id,))
        user = cursor.fetchone()
        first_name = user[0] if user and user[0] else "Пользователь"
        username = user[1] if user and user[1] else "без username"

        await callback.message.answer(
            f"🚫 Пользователь заблокирован!\n"
            f"👤 {first_name} (@{username})\n"
            f"🆔 ID: {target_user_id}"
        )

        try:
            await bot.send_message(
                target_user_id,
                "🚫 Ваш доступ к боту был заблокирован администратором."
            )
        except Exception as e:
            logger.error(f"Не удалось уведомить пользователя {target_user_id}: {e}")

        await callback.answer()
        await log_action(admin_id, "Блокировка пользователя", f"ID: {target_user_id}")

    except Exception as e:
        logger.error(f"Ошибка при блокировке пользователя: {e}")
        await callback.answer("❌ Ошибка при блокировке пользователя")


@dp.callback_query(F.data.startswith("unban_"))
async def unban_user_callback(callback: types.CallbackQuery):
    try:
        target_user_id = int(callback.data.split("_")[1])
        admin_id = callback.from_user.id

        cursor.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (target_user_id,))
        conn.commit()

        cursor.execute("SELECT first_name, username FROM users WHERE user_id = ?", (target_user_id,))
        user = cursor.fetchone()
        first_name = user[0] if user and user[0] else "Пользователь"
        username = user[1] if user and user[1] else "без username"

        await callback.message.answer(
            f"✅ Пользователь разблокирован!\n"
            f"👤 {first_name} (@{username})\n"
            f"🆔 ID: {target_user_id}"
        )

        try:
            await bot.send_message(
                target_user_id,
                "✅ Ваш доступ к боту был восстановлен администратором."
            )
        except Exception as e:
            logger.error(f"Не удалось уведомить пользователя {target_user_id}: {e}")

        await callback.answer()
        await log_action(admin_id, "Разблокировка пользователя", f"ID: {target_user_id}")

    except Exception as e:
        logger.error(f"Ошибка при разблокировке пользователя: {e}")
        await callback.answer("❌ Ошибка при разблокировке пользователя")


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
    await list_all_users(message)


@dp.message(F.text == "📊 Статистика")
@admin_required
async def admin_stats(message: types.Message):
    try:
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1")
        admin_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
        banned_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM users WHERE is_approved = 1")
        approved_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM users WHERE is_approved = 0 AND is_banned = 0")
        pending_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM products")
        total_products = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM products WHERE quantity < 10")
        low_stock = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM shift_reports")
        total_reports = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM action_logs WHERE timestamp > datetime('now', '-1 day')")
        actions_24h = cursor.fetchone()[0]

        response = (
            f"📊 Статистика бота:\n\n"
            f"👥 Пользователи:\n"
            f"├ Всего: {total_users}\n"
            f"├ Администраторы: {admin_count}\n"
            f"├ Одобренные: {approved_count}\n"
            f"├ Ожидают одобрения: {pending_count}\n"
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
                    [KeyboardButton(text="🏷 Изменить категориу")],
                    [KeyboardButton(text="🔙 К списку товаров")]
                ],
                resize_keyboard=True
            )
        )

    except Exception as e:
        logger.error(f"Ошибка при выборе товара: {e}")
        await message.answer("❌ Ошибка при выборе товара!", reply_markup=get_warehouse_keyboard())


@dp.message(F.text == "🔙 К списку товаров")
async def back_to_products_list(message: types.Message):
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
        logger.error(f"❌ Ошибка при экспорте: {str(e)}", exc_info=True)
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
            'fields': ['total', 'cash', 'card', 'bar', 'hookah_count', 'expenses'],
            'current_field': 0,
            'labels': [
                "общую сумму выручки",
                "сумму наличных",
                "сумму безналичных",
                "выручку по бару",
                "количество проданных кальянов",
                "сумму расходов"
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
        "SELECT total, cash, card, bar, hookah_count, expenses "
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
            'fields': ['total', 'cash', 'card', 'bar', 'hookah_count', 'expenses'],
            'current_field': 0,
            'values': list(report),
            'labels': [
                "общую сумму выручки",
                "сумму наличных",
                "сумму безналичных",
                "выручку по бару",
                "количество проданных кальянов",
                "сумму расходов"
            ]
        }
    }

    await message.answer(
        f"🔄 Обновление отчёта за {today}\n"
        f"Текущее значение {user_data[user_id]['report']['labels'][0]}: "
        f"{user_data[user_id]['report']['values'][0]}\n"
        f"Введите новое значение или нажмите '⏭ Пропустить':",
        reply_markup=get_skip_keyboard()
    )


@dp.message(F.text, lambda message: user_states.get(message.from_user.id) in ["report_date", "update_report"])
async def process_report_data(message: types.Message):
    user_id = message.from_user.id
    state = user_states[user_id]
    report_data = user_data[user_id]['report']
    current_field = report_data['current_field']
    field_name = report_data['fields'][current_field]

    # Обработка отмены
    if message.text == "❌ Отмена":
        user_states[user_id] = None
        if 'report' in user_data[user_id]:
            del user_data[user_id]['report']
        await message.answer("❌ Создание отчета отменено", reply_markup=get_report_keyboard())
        return

    # Обработка пропуска (только для обновления)
    if state == "update_report" and message.text == "⏭ Пропустить":
        report_data['current_field'] += 1

        if report_data['current_field'] < len(report_data['fields']):
            next_index = report_data['current_field']
            next_label = report_data['labels'][next_index]
            current_value = report_data['values'][next_index]

            await message.answer(
                f"Текущее значение {next_label}: {current_value}\n"
                f"Введите новое значение или нажмите '⏭ Пропустить':",
                reply_markup=get_skip_keyboard()
            )
        else:
            await save_report(message, user_id, state, report_data)
        return

    # Проверка введенных данных
    try:
        if field_name == 'hookah_count':
            value = int(message.text)
        else:
            value = float(message.text.replace(',', '.'))

        if value < 0:
            raise ValueError("Отрицательное значение")
    except:
        error_msg = "❌ Ошибка! Введите корректное положительное число."
        if state == "update_report":
            error_msg += "\nИли нажмите '⏭ Пропустить' чтобы оставить текущее значение."
            await message.answer(error_msg, reply_markup=get_skip_keyboard())
        else:
            await message.answer(error_msg, reply_markup=get_cancel_keyboard())
        return

    if state == "report_date":
        report_data[field_name] = value
    else:
        report_data['values'][current_field] = value

    report_data['current_field'] += 1

    if report_data['current_field'] < len(report_data['fields']):
        next_index = report_data['current_field']
        next_label = report_data['labels'][next_index]

        if state == "update_report":
            current_value = report_data['values'][next_index]
            await message.answer(
                f"Текущее значение {next_label}: {current_value}\n"
                f"Введите новое значение или нажмите '⏭ Пропустить':",
                reply_markup=get_skip_keyboard()
            )
        else:
            await message.answer(f"Введите {next_label}:", reply_markup=get_cancel_keyboard())
    else:
        await save_report(message, user_id, state, report_data)


async def save_report(message: types.Message, user_id: int, state: str, report_data: dict):
    try:
        # Рассчитываем баланс: initial_cash + cash - expenses
        initial_cash = 4000
        cash = report_data['cash'] if state == "report_date" else report_data['values'][1]
        expenses = report_data['expenses'] if state == "report_date" else report_data['values'][5]
        balance = initial_cash + cash - expenses

        if state == "report_date":
            cursor.execute(
                "INSERT INTO shift_reports "
                "(user_id, report_date, total, cash, card, bar, hookah_count, expenses, initial_cash, balance) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, report_data['report_date'],
                 report_data['total'], report_data['cash'], report_data['card'],
                 report_data['bar'], report_data['hookah_count'], report_data['expenses'],
                 initial_cash, balance)
            )
            action = "создан"
            report_values = [
                report_data['total'], report_data['cash'], report_data['card'],
                report_data['bar'], report_data['hookah_count'], report_data['expenses'],
                balance
            ]
        else:
            cursor.execute(
                "UPDATE shift_reports SET "
                "total = ?, cash = ?, card = ?, bar = ?, "
                "hookah_count = ?, expenses = ?, balance = ? "
                "WHERE user_id = ? AND report_date = ?",
                (report_data['values'][0], report_data['values'][1],
                 report_data['values'][2], report_data['values'][3],
                 report_data['values'][4], report_data['values'][5],
                 balance, user_id, report_data['report_date'])
            )
            action = "обновлен"
            report_values = report_data['values'] + [balance]

        conn.commit()

        report_text = (
            f"📝 Отчёт по смене {report_data['report_date']} {action}:\n\n"
            f"• Общая сумма: {report_values[0]} ₽\n"
            f"• Наличные: {report_values[1]} ₽\n"
            f"• Безналичные: {report_values[2]} ₽\n"
            f"• Бар: {report_values[3]} ₽\n"
            f"• Кальяны: {report_values[4]} шт.\n"
            f"• Расходы: {report_values[5]} ₽\n"
            f"• Начальная касса: 4000 ₽\n"
            f"• Остаток: {report_values[6]} ₽\n\n"
            f"💸 Чистая прибыль: {report_values[0] - report_values[5]} ₽"
        )

        await message.answer(report_text, reply_markup=get_report_keyboard())
        await log_action(user_id, f"Отчёт {action}", f"Дата: {report_data['report_date']}")

        # Отправка отчета в настроенную группу
        report_chat_id = get_notification_chat("reports")
        if report_chat_id:
            try:
                cursor.execute("SELECT first_name, username FROM users WHERE user_id = ?", (user_id,))
                user_info = cursor.fetchone()
                first_name = user_info[0] if user_info and user_info[0] else "Неизвестный"
                username = f"@{user_info[1]}" if user_info and user_info[1] else "без username"

                group_report = (
                    f"📊 Отчет по смене за {report_data['report_date']}\n"
                    f"👤 Ответственный: {first_name} ({username})\n\n"
                    f"💰 Общая выручка: {report_values[0]} ₽\n"
                    f"💵 Наличные: {report_values[1]} ₽\n"
                    f"💳 Безналичные: {report_values[2]} ₽\n"
                    f"🍻 Выручка по бару: {report_values[3]} ₽\n"
                    f"🚬 Количество кальянов: {report_values[4]} шт.\n"
                    f"📦 Расходы: {report_values[5]} ₽\n"
                    f"🏦 Начальная касса: 4000 ₽\n"
                    f"💸 Остаток в кассе: {report_values[6]} ₽\n\n"
                    f"💵 Чистая прибыль: {report_values[0] - report_values[5]} ₽"
                )

                await bot.send_message(report_chat_id, group_report)
                await log_action(user_id, "Отправка отчета в группу", f"Группа: {report_chat_id}")
            except Exception as e:
                logger.error(f"Ошибка отправки отчета в группу: {e}")
                await message.answer("❌ Не удалось отправить отчет в группу", reply_markup=get_report_keyboard())

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
            "SELECT report_date, total, cash, card, bar, hookah_count, expenses, balance "
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
                f"├ Кальяны: {report[5]} шт.\n"
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
        if state.startswith(("adding_", "searching", "editing_")):
            user_states[user_id] = None
            if user_id in user_data:
                user_data[user_id] = {}
            await message.answer("❌ Действие отменено", reply_markup=get_warehouse_keyboard())
        elif state in ["report_date", "update_report"]:
            user_states[user_id] = None
            if user_id in user_data and 'report' in user_data[user_id]:
                del user_data[user_id]['report']
            await message.answer("❌ Действие отменено", reply_markup=get_report_keyboard())
        elif state.endswith(("_user")):
            user_states[user_id] = None
            await message.answer("❌ Действие отменено", reply_markup=get_user_management_keyboard())
    else:
        await message.answer("❌ Нет активных действий для отмены", reply_markup=get_main_keyboard(user_id))


# ===== ОБРАБОТЧИК КНОПКИ "НАЗАД" =====
@dp.message(F.text == "🔙 Назад")
async def back_handler(message: types.Message):
    user_id = message.from_user.id

    if user_states.get(user_id) in ["editing_name", "editing_quantity", "editing_category"]:
        user_states[user_id] = None
        await message.answer("❌ Изменение товара отменено", reply_markup=get_warehouse_keyboard())
        return

    if user_data.get(user_id) and "edit_id" in user_data[user_id]:
        await edit_product_start(message)
        return

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
    logger.info("=" * 50)
    logger.info(f"🤖 ЗАПУСК СИСТЕМЫ SoraEcoSystemBot")
    logger.info(f"⏰ Время запуска: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"🔑 ID главного администратора: {MAIN_ADMIN_ID}")

    if not is_registered(MAIN_ADMIN_ID):
        cursor.execute(
            "INSERT INTO users (user_id, username, first_name, is_admin, is_approved) VALUES (?, ?, ?, ?, ?)",
            (MAIN_ADMIN_ID, "sora_admin", "Sora Admin", 1, 1)
        )
        conn.commit()
        logger.info("✅ Главный администратор зарегистрирован")

    try:
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM products")
        product_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM action_logs")
        log_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM users WHERE is_approved = 1")
        approved_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_approved = 0 AND is_banned = 0")
        pending_count = cursor.fetchone()[0]

        logger.info(f"👥 Пользователей в системе: {user_count}")
        logger.info(f"├ Одобренные: {approved_count}")
        logger.info(f"└ Ожидают одобрения: {pending_count}")
        logger.info(f"📦 Товаров на складе: {product_count}")
        logger.info(f"📝 Лог-записей действий: {log_count}")
        logger.info("=" * 50)
    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {e}")

    logger.info("🟢 Бот запущен и готов к работе")
    try:
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logger.info("⏹️ Получен сигнал остановки (Ctrl+C)")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при работе бота: {e}")
    finally:
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