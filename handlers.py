from aiogram import Router
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.filters import Command
from parser import (
    add_user_source,
    get_user_sources,
    get_latest_news,
    get_random_news,
    get_top_news,
    load_user_sources,
    remove_user_source,
)
from keyboards import (
    categories_menu,
    main_menu,
    manage_sources_menu,
    sources_menu,
    user_sources_menu,
)
from config import NEWS_CATEGORIES, GROUPS_FILE
from logger import logger  # Импортируем логер

from aiogram.filters import ChatMemberUpdatedFilter, IS_NOT_MEMBER, IS_MEMBER
from aiogram.types import ChatMemberUpdated

router = Router()
user_states = {}

@router.message(Command("start"))
async def start(message: Message):
    logger.info(f"Пользователь {message.from_user.id} начал работу с ботом.")
    await message.answer("Привет! Выбери действие:", reply_markup=main_menu())

@router.message(Command("help"))
async def help(message: Message):
    text = """
    📜 Доступные команды:
    /start - Запустить бота
    /help - Помощь
    /sources - Управление источниками
    /news - Случайные новости
    """
    await message.answer(text)

@router.message(Command("sources"))
async def handle_sources_command(message: Message):
    await message.answer("Управление источниками:", reply_markup=manage_sources_menu())

@router.message(Command("news"))
async def random_news(message: Message):
    news_list = await get_random_news(str(message.from_user.id))

    if not news_list or not isinstance(news_list, list):
        await message.answer("😢 Не удалось загрузить новости.")
        return

    valid_news = [news for news in news_list if isinstance(news, str) and news.strip()]
    if not valid_news:
        await message.answer("😢 Не удалось загрузить новости.")
        return

    for news in valid_news:
        await message.answer(news)

@router.message(lambda message: message.text == "⚙️ Управление источниками")
async def handle_sources_button(message: Message):
    await message.answer("Управление источниками:", reply_markup=manage_sources_menu())

@router.message(lambda message: message.text == "📰 Новости по источнику")
async def handle_choose_news_source(message: Message):
    logger.info(f"Пользователь {message.from_user.id} выбрал новости по источнику.")
    user_id = str(message.from_user.id)
    await message.answer(
        "Выбери источник:",
        reply_markup=sources_menu(user_id)
    )

@router.message(lambda message: message.text == "📂 Новости по категории")
async def handle_choose_category_button(message: Message):
    logger.info(f"Пользователь {message.from_user.id} выбрал новости по категории.")
    await message.answer("Выбери категорию:", reply_markup=categories_menu())

@router.message(lambda message: message.text == "🎲 Рандомные новости")
async def handle_random_news_button(message: Message):
    user_id = str(message.from_user.id)
    logger.info(f"Пользователь {user_id} запросил случайные новости.")
    news_list = await get_random_news(user_id)  # Добавьте await
    for news in news_list:
        await message.answer(news)

@router.message(lambda message: message.text == "📌 Основные новости")
async def handle_top_news_button(message: Message):
    user_id = str(message.from_user.id)
    news_list = await get_top_news(user_id)
    
    if not news_list:
        await message.answer("😢 Нет свежих главных новостей.")
        return
    
    await message.answer(
        "📌 <b>Главные новости:</b>\n\n" + "\n".join(news_list),
        parse_mode="HTML",
        disable_web_page_preview=True
    )

@router.message(lambda message: message.text == "➕ Добавить источник")
async def handle_add_source_button(message: Message):
    user_id = str(message.from_user.id)
    logger.info(f"Пользователь {user_id} начал добавление источника.")
    user_states[user_id] = "waiting_for_source_name"  # Состояние: ожидание названия
    await message.answer("Введите название нового источника:", reply_markup=ReplyKeyboardRemove())

@router.message(lambda message: message.text == "🔙 Назад" 
                and user_states.get(str(message.from_user.id)) == "waiting_source_to_remove")
async def handle_back_during_removal(message: Message):
    user_id = str(message.from_user.id)
    del user_states[user_id]  # Сбрасываем состояние
    await message.answer("Возвращаемся в меню управления:", reply_markup=manage_sources_menu())

@router.message(lambda message: message.text == "🔙 Назад")
async def handle_back_button(message: Message):
    logger.info(f"Пользователь {message.from_user.id} нажал кнопку 'Назад'.")
    user_id = str(message.from_user.id)
    if user_id in user_states:
        del user_states[user_id]  # Сбрасываем состояние
    await message.answer("Возвращаемся в главное меню:", reply_markup=main_menu())

@router.message(lambda message: message.text == "➖ Удалить источник")
async def handle_remove_source_button(message: Message):
    user_id = str(message.from_user.id)
    user_sources = load_user_sources().get(user_id, {})
    
    if not user_sources:
        await message.answer("❌ У вас нет пользовательских источников.")
        return
    
    user_states[user_id] = "waiting_source_to_remove"
    await message.answer("Выберите источник для удаления:", 
                        reply_markup=user_sources_menu(user_id))  # Используем существующее меню
    
# Обработчик удаления источника (должен быть ПЕРВЫМ)
@router.message(lambda message: user_states.get(str(message.from_user.id)) == "waiting_source_to_remove")
async def handle_source_removal(message: Message):
    user_id = str(message.from_user.id)
    source_name = message.text
    result = remove_user_source(user_id, source_name)
    
    if "✅" in result:
        del user_states[user_id]  # Сбрасываем состояние только при успешном удалении
    
    await message.answer(result, reply_markup=manage_sources_menu())

@router.message(lambda message: message.text == "📋 Мои источники")
async def handle_show_user_sources_button(message: Message):
    user_id = str(message.from_user.id)
    user_sources = load_user_sources().get(user_id, {})
    
    if not user_sources:
        await message.answer("📭 У вас пока нет своих источников.")
        return
    
    text = "📋 Ваши источники:\n" + "\n".join(
        [f"• {name} ({url})" for name, url in user_sources.items()]
    )
    await message.answer(text)

@router.message(
    lambda message: message.text in get_user_sources(str(message.from_user.id))
)
async def handle_send_source_news(message: Message):
    user_id = str(message.from_user.id)
    source = message.text
    logger.info(f"Пользователь {user_id} запросил новости из источника: {source}.")
    
    news_list = await get_latest_news(user_id, source)
    
    if not news_list:
        await message.answer("😢 Не удалось загрузить новости.")
        return
    
    for news in news_list:
        await message.answer(news)  # Теперь news гарантированно строка

@router.message(lambda message: message.text in NEWS_CATEGORIES)
async def handle_send_category_news(message: Message):
    user_id = str(message.from_user.id)
    category = message.text
    logger.info(f"Пользователь {user_id} запросил новости из категории: {category}.")
    
    news_list = await get_latest_news(user_id, category, is_category=True)
    
    if not news_list:
        await message.answer("😢 В этой категории пока нет новостей.")
        return
    
    for news in news_list:
        await message.answer(news)


@router.message()
async def handle_custom_source(message: Message):
    user_id = str(message.from_user.id)
    logger.info(f"Пользователь {user_id} отправил сообщение: {message.text}")
    # Если сообщение совпадает с кнопками → пропускаем обработку
    if message.text in ["📰 Новости по источнику", "📂 Новости по категории", "🎲 Рандомные новости", "➕ Добавить источник", "🔙 Назад"]:
        return
    
    if user_states.get(user_id) == "waiting_source_to_remove":
        source_name = message.text
        result = remove_user_source(user_id, source_name)
        del user_states[user_id]
        await message.answer(result, reply_markup=manage_sources_menu())
        return
    
    if user_states.get(user_id) == "waiting_for_source_name":
        logger.info(f"Пользователь {user_id} ввел название источника: {message.text}")
        # Пользователь ввел название → переводим в состояние ожидания ссылки
        user_states[user_id] = {"status": "waiting_for_url", "source_name": message.text}
        await message.answer("Теперь отправьте ссылку на RSS-ленту:")
    
    elif user_states.get(user_id) and user_states[user_id].get("status") == "waiting_for_url":
        logger.info(f"Пользователь {user_id} ввел ссылку: {message.text}")
        # Пользователь ввел ссылку → сохраняем источник
        source_name = user_states[user_id]["source_name"]
        url = message.text
        result = add_user_source(user_id, source_name, url)
        await message.answer(result, reply_markup=sources_menu(user_id))
        del user_states[user_id]  # Удаляем состояние
        await message.answer(result, reply_markup=main_menu())
    
    else:
        # Если сообщение не обработано другими обработчиками
        await message.answer("Не понимаю команду 😢")


@router.chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER))
async def on_bot_added_to_group(event: ChatMemberUpdated):
    """Обработчик добавления бота в группу"""
    chat_id = event.chat.id
    with open(GROUPS_FILE, "a+") as f:
        f.seek(0)
        existing_ids = f.read().splitlines()
        if str(chat_id) not in existing_ids:
            f.write(f"{chat_id}\n")
            logger.info(f"Бот добавлен в группу {chat_id}")

@router.chat_member(ChatMemberUpdatedFilter(IS_MEMBER >> IS_NOT_MEMBER))
async def on_bot_removed_from_group(event: ChatMemberUpdated):
    """Обработчик удаления бота из группы"""
    chat_id = event.chat.id
    with open(GROUPS_FILE, "r+") as f:
        lines = f.readlines()
        f.seek(0)
        f.truncate()
        for line in lines:
            if line.strip() != str(chat_id):
                f.write(line)
    logger.info(f"Бот удален из группы {chat_id}")
