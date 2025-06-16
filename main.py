import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, FSInputFile
import sqlite3
import asyncio
import os
from pathlib import Path
import pandas as pd
from datetime import datetime
from io import BytesIO
from openpyxl import Workbook
from aiogram.types import BufferedInputFile

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
DB_PATH = BASE_DIR / "warehouse.db"  # Теперь в корне проекта
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
conn.commit()


# ===== КЛАВИАТУРЫ =====
def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📦 Добавить товар")],
            [KeyboardButton(text="📊 Посмотреть склад"), KeyboardButton(text="🔍 Поиск товара")],
            [KeyboardButton(text="✏️ Редактировать"), KeyboardButton(text="❌ Удалить товар")],
            [KeyboardButton(text="📥 Экспорт в Excel")]
        ],
        resize_keyboard=True
    )


# ===== КОМАНДА /start =====
@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = message.from_user.id
    user_states[user_id] = None
    user_data[user_id] = {}
    await message.answer(
        "🛒 Добро пожаловать в складской бот!\n"
        "Выберите действие из меню ниже:",
        reply_markup=get_main_keyboard()
    )


# ===== ДОБАВЛЕНИЕ ТОВАРА =====
@dp.message(F.text == "📦 Добавить товар")
async def add_product_start(message: types.Message):
    user_id = message.from_user.id
    user_states[user_id] = "adding_name"
    user_data[user_id] = {}
    await message.answer("Введите название товара:")


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
            reply_markup=get_main_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка при добавлении товара: {e}")
        await message.answer("❌ Произошла ошибка при добавлении товара!", reply_markup=get_main_keyboard())
    finally:
        user_states[user_id] = None
        user_data[user_id] = {}


# ===== ПОИСК ТОВАРА =====
@dp.message(F.text == "🔍 Поиск товара")
async def search_product_start(message: types.Message):
    user_states[message.from_user.id] = "searching"
    await message.answer("Введите название товара или категории для поиска:")


@dp.message(F.text, lambda message: user_states.get(message.from_user.id) == "searching")
async def search_product_execute(message: types.Message):
    user_id = message.from_user.id
    search_term = f"%{message.text}%"

    try:
        cursor.execute(
            "SELECT * FROM products WHERE name LIKE ? OR category LIKE ?",
            (search_term, search_term)
        )
        products = cursor.fetchall()

        if not products:
            await message.answer("🔎 Товары не найдены", reply_markup=get_main_keyboard())
            user_states[user_id] = None
            return

        response = "🔍 Результаты поиска:\n\n"
        for product in products:
            response += (f"🔹 ID: {product[0]}\n"
                         f"Название: {product[1]}\n"
                         f"Количество: {product[2]}\n"
                         f"Категория: {product[3] if product[3] else 'не указана'}\n\n")

        await message.answer(response, reply_markup=get_main_keyboard())
    except Exception as e:
        logger.error(f"Ошибка при поиске товара: {e}")
        await message.answer("❌ Произошла ошибка при поиске товара!", reply_markup=get_main_keyboard())
    finally:
        user_states[user_id] = None


# ===== РЕДАКТИРОВАНИЕ ТОВАРА =====
@dp.message(F.text == "✏️ Редактировать")
async def edit_product_start(message: types.Message):
    # Получаем список товаров из базы
    cursor.execute("SELECT id, name, quantity FROM products")
    products = cursor.fetchall()

    if not products:
        await message.answer("📭 Склад пуст! Нечего редактировать.", reply_markup=get_main_keyboard())
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
            await message.answer("❌ Товар не найден!", reply_markup=get_main_keyboard())
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
        await message.answer("❌ Ошибка при выборе товара!", reply_markup=get_main_keyboard())


# Обработчики выбора действия
@dp.message(F.text == "🖊 Изменить название")
async def edit_name_handler(message: types.Message):
    user_states[message.from_user.id] = "editing_name"
    await message.answer("Введите новое название:", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Отмена")]],
        resize_keyboard=True
    ))


@dp.message(F.text == "🔢 Изменить количество")
async def edit_quantity_handler(message: types.Message):
    user_states[message.from_user.id] = "editing_quantity"
    await message.answer("Введите новое количество:", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Отмена")]],
        resize_keyboard=True
    ))


@dp.message(F.text == "🏷 Изменить категорию")
async def edit_category_handler(message: types.Message):
    user_states[message.from_user.id] = "editing_category"
    await message.answer(
        "Введите новую категорию или 'удалить' чтобы удалить категорию:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="🔙 Отмена")]],
            resize_keyboard=True
        )
    )


# Обработчики ввода новых значений
@dp.message(F.text, lambda message: user_states.get(message.from_user.id) == "editing_name")
async def save_new_name(message: types.Message):
    if message.text == "🔙 Отмена":
        await message.answer("Изменение названия отменено", reply_markup=get_main_keyboard())
    else:
        product_id = user_data[message.from_user.id]["edit_id"]
        cursor.execute("UPDATE products SET name = ? WHERE id = ?", (message.text, product_id))
        conn.commit()
        await message.answer(f"✅ Название изменено на: {message.text}", reply_markup=get_main_keyboard())
    user_states[message.from_user.id] = None


@dp.message(F.text, lambda message: user_states.get(message.from_user.id) == "editing_quantity")
async def save_new_quantity(message: types.Message):
    if message.text == "🔙 Отмена":
        await message.answer("Изменение количества отменено", reply_markup=get_main_keyboard())
    elif not message.text.isdigit():
        await message.answer("❌ Введите число!")
    else:
        product_id = user_data[message.from_user.id]["edit_id"]
        cursor.execute("UPDATE products SET quantity = ? WHERE id = ?", (int(message.text), product_id))
        conn.commit()
        await message.answer(f"✅ Количество изменено на: {message.text}", reply_markup=get_main_keyboard())
    user_states[message.from_user.id] = None


@dp.message(F.text, lambda message: user_states.get(message.from_user.id) == "editing_category")
async def save_new_category(message: types.Message):
    if message.text == "🔙 Отмена":
        await message.answer("Изменение категории отменено", reply_markup=get_main_keyboard())
    else:
        product_id = user_data[message.from_user.id]["edit_id"]
        new_category = None if message.text.lower() == "удалить" else message.text
        cursor.execute("UPDATE products SET category = ? WHERE id = ?", (new_category, product_id))
        conn.commit()
        action = "удалена" if new_category is None else "изменена"
        await message.answer(f"✅ Категория {action}", reply_markup=get_main_keyboard())
    user_states[message.from_user.id] = None


# ===== УДАЛЕНИЕ ТОВАРА =====
@dp.message(F.text == "❌ Удалить товар")
async def delete_product_start(message: types.Message):
    # Получаем список товаров из базы
    cursor.execute("SELECT id, name FROM products")
    products = cursor.fetchall()

    if not products:
        await message.answer("📭 Склад пуст! Нечего удалять.", reply_markup=get_main_keyboard())
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
            await message.answer("❌ Товар не найден!", reply_markup=get_main_keyboard())
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
            reply_markup=get_main_keyboard()
        )

    except Exception as e:
        logger.error(f"Ошибка при удалении товара: {e}")
        await message.answer("❌ Произошла ошибка при удалении товара!", reply_markup=get_main_keyboard())


# Обработчик кнопки "Назад"
@dp.message(F.text == "🔙 Назад")
async def back_to_main_menu(message: types.Message):
    await message.answer("Главное меню:", reply_markup=get_main_keyboard())


# ===== ВЫВОД СПИСКА ТОВАРОВ =====
@dp.message(F.text == "📊 Посмотреть склад")
async def show_warehouse(message: types.Message):
    user_id = message.from_user.id
    user_states[user_id] = None

    try:
        cursor.execute("SELECT * FROM products")
        products = cursor.fetchall()

        if not products:
            await message.answer("📭 Склад пуст!", reply_markup=get_main_keyboard())
            return

        response = "📋 Список товаров:\n\n"
        for product in products:
            response += (
                f"🔹 ID: {product[0]}\n"
                f"Название: {product[1]}\n"
                f"Количество: {product[2]}\n"
                f"Категория: {product[3] if product[3] else 'не указана'}\n"
                f"Добавлен: {product[4]}\n\n"
            )

        # Разбиваем сообщение на части, если оно слишком длинное
        max_length = 4000
        for i in range(0, len(response), max_length):
            await message.answer(response[i:i + max_length])

    except Exception as e:
        logger.error(f"Ошибка при выводе склада: {e}")
        await message.answer("❌ Произошла ошибка при получении данных склада!", reply_markup=get_main_keyboard())


# ===== ЭКСПОРТ В EXCEL =====
@dp.message(F.text == "📥 Экспорт в Excel")
async def export_to_excel(message: types.Message):
    try:
        # Получаем данные из базы
        cursor.execute("SELECT id, name, quantity, category, added_date FROM products")
        columns = [column[0] for column in cursor.description]
        data = cursor.fetchall()

        if not data:
            await message.answer("📭 Склад пуст! Нет данных для экспорта.", reply_markup=get_main_keyboard())
            return

        # Создаем временный файл в памяти
        output = BytesIO()

        # Создаем Excel-файл
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Склад"

        # Записываем заголовки
        sheet.append(columns)

        # Записываем данные
        for row in data:
            sheet.append(row)

        # Сохраняем в буфер
        workbook.save(output)
        output.seek(0)

        # Формируем имя файла
        filename = f"склад_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.xlsx"

        # Отправляем файл пользователю
        await message.answer_document(
            document=types.BufferedInputFile(output.read(), filename=filename),
            caption="📊 Экспорт данных склада в Excel"
        )

        await message.answer("✅ Экспорт успешно завершен!", reply_markup=get_main_keyboard())

    except Exception as e:
        logger.error(f"Ошибка при экспорте: {str(e)}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при экспорте данных!\n"
            f"Ошибка: {str(e)}",
            reply_markup=get_main_keyboard()
        )


# ===== ЗАПУСК БОТА =====
async def main():
    # Проверка базы при запуске
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='products'")
    table_exists = cursor.fetchone()
    logger.info(f"Таблица 'products' существует: {bool(table_exists)}")

    cursor.execute("SELECT COUNT(*) FROM products")
    count = cursor.fetchone()[0]
    logger.info(f"Количество товаров в базе при запуске: {count}")

    # Запускаем бота
    await dp.start_polling(bot)
    logger.info("Бот запущен!")


if __name__ == "__main__":
    asyncio.run(main())