from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from config import NEWS_SOURCES, NEWS_CATEGORIES
from parser import get_user_sources, load_user_sources

def main_menu():
    """Главное меню"""
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📰 Новости по источнику"), KeyboardButton(text="📂 Новости по категории")],
        [KeyboardButton(text="🎲 Рандомные новости"), KeyboardButton(text="📌 Основные новости")],
        [KeyboardButton(text="⚙️ Управление источниками")]
    ], resize_keyboard=True)

def sources_menu(user_id: str):
    """Кнопки выбора источников"""
    all_sources = get_user_sources(user_id)  # Получаем ВСЕ источники
    sources = list(all_sources.keys())       # Названия источников
    buttons = []
    
    # Группируем кнопки по две в ряд
    for i in range(0, len(sources), 2):
        row = sources[i:i+2]
        buttons.append([KeyboardButton(text=source) for source in row])
    
    # Добавляем кнопку "Назад" в отдельный ряд
    buttons.append([KeyboardButton(text="🔙 Назад")])
    
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def categories_menu():
    """Кнопки выбора категорий"""
    categories = list(NEWS_CATEGORIES.keys())
    buttons = []
    
    # Группируем кнопки по две в ряд
    for i in range(0, len(categories), 2):
        row = categories[i:i+2]
        buttons.append([KeyboardButton(text=category) for category in row])
    
    # Добавляем кнопку "Назад" в отдельный ряд
    buttons.append([KeyboardButton(text="🔙 Назад")])
    
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def manage_sources_menu():
    """Меню управления источниками"""
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Добавить источник"), KeyboardButton(text="➖ Удалить источник")],
        [KeyboardButton(text="📋 Мои источники")],
        [KeyboardButton(text="🔙 Назад")]
    ], resize_keyboard=True)

def user_sources_menu(user_id: str):
    """Меню только пользовательских источников для удаления"""
    user_sources = load_user_sources().get(user_id, {})
    sources = list(user_sources.keys())
    
    buttons = []
    for i in range(0, len(sources), 2):
        row = sources[i:i+2]
        buttons.append([KeyboardButton(text=source) for source in row])
    
    buttons.append([KeyboardButton(text="🔙 Назад")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
