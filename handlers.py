from aiogram import Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardRemove,
)
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from parser import (
    add_user_source,
    get_preferences,
    get_user_sources,
    get_latest_news,
    get_random_news,
    get_top_news,
    remove_user_source,
    update_preferences,
)
from keyboards import (
    categories_menu,
    feed_settings_menu,
    main_menu,
    manage_sources_menu,
    sources_menu,
    user_sources_menu,
)
from config import NEWS_CATEGORIES
from logger import logger  # Импортируем логер
from storage.db import add_bot_group, get_user_sources_for_user, remove_bot_group
from formatters import format_news_batch
from uuid import uuid4

from aiogram.filters import ChatMemberUpdatedFilter, IS_NOT_MEMBER, IS_MEMBER
from aiogram.types import ChatMemberUpdated
from urllib.parse import urlparse

router = Router()

NEWS_BATCH_SIZE = 4
news_sessions: dict[str, dict] = {}


def _build_news_keyboard(session_id: str, page: int, total_items: int) -> InlineKeyboardMarkup:
    next_exists = (page + 1) * NEWS_BATCH_SIZE < total_items
    buttons = []

    if next_exists:
        buttons.append(InlineKeyboardButton(text="Ещё", callback_data=f"news:more:{session_id}:{page + 1}"))

    buttons.append(InlineKeyboardButton(text="Сменить источник", callback_data=f"news:switch:{session_id}:{page}"))
    buttons.append(InlineKeyboardButton(text="Скрыть", callback_data=f"news:hide:{session_id}:{page}"))

    return InlineKeyboardMarkup(inline_keyboard=[buttons])


async def _send_news_batch(message: Message, user_id: str, news_list: list[str], title: str, origin: str):
    valid_news = [news for news in news_list if isinstance(news, str) and news.strip()]
    if not valid_news:
        await message.answer("😢 Не удалось загрузить новости.")
        return

    session_id = uuid4().hex[:8]
    news_sessions[session_id] = {
        "user_id": user_id,
        "items": valid_news,
        "title": title,
        "origin": origin,
    }

    first_batch = valid_news[:NEWS_BATCH_SIZE]
    text = format_news_batch(first_batch, start_index=1, title=title)
    keyboard = _build_news_keyboard(session_id, page=0, total_items=len(valid_news))
    await message.answer(text, parse_mode="HTML", disable_web_page_preview=True, reply_markup=keyboard)


def is_http_url(message: Message) -> bool:
    text = (message.text or "").strip()
    if not text:
        return False
    parsed = urlparse(text)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


class SourceForm(StatesGroup):
    waiting_for_source_name = State()
    waiting_for_source_url = State()
    waiting_source_to_remove = State()

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
    await _send_news_batch(message, str(message.from_user.id), news_list, "🎲 Случайные новости", "random")

@router.message(lambda message: message.text == "⚙️ Управление источниками")
async def handle_sources_button(message: Message):
    await message.answer("Управление источниками:", reply_markup=manage_sources_menu())


@router.message(lambda message: message.text == "⚙️ Настройки ленты")
async def handle_feed_settings_button(message: Message):
    chat_id = str(message.chat.id)
    preferences = await get_preferences(chat_id)
    text = (
        "⚙️ <b>Настройки ленты</b>\n"
        "Выберите параметр для изменения.\n"
        "Эти настройки применяются к текущему чату."
    )
    await message.answer(text, parse_mode="HTML", reply_markup=feed_settings_menu(preferences))

@router.message(lambda message: message.text == "📰 Новости по источнику")
async def handle_choose_news_source(message: Message):
    logger.info(f"Пользователь {message.from_user.id} выбрал новости по источнику.")
    user_id = str(message.from_user.id)
    await message.answer(
        "Выбери источник:",
        reply_markup=await sources_menu(user_id)
    )

@router.message(lambda message: message.text == "📂 Новости по категории")
async def handle_choose_category_button(message: Message):
    logger.info(f"Пользователь {message.from_user.id} выбрал новости по категории.")
    await message.answer("Выбери категорию:", reply_markup=categories_menu())

@router.message(lambda message: message.text == "🎲 Рандомные новости")
async def handle_random_news_button(message: Message):
    user_id = str(message.from_user.id)
    logger.info(f"Пользователь {user_id} запросил случайные новости.")
    news_list = await get_random_news(user_id)
    await _send_news_batch(message, user_id, news_list, "🎲 Случайные новости", "random")

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
async def handle_add_source_button(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    logger.info(f"Пользователь {user_id} начал добавление источника.")
    await state.set_state(SourceForm.waiting_for_source_name)
    await message.answer("Введите название нового источника:", reply_markup=ReplyKeyboardRemove())

@router.message(StateFilter(SourceForm.waiting_source_to_remove), lambda message: message.text == "🔙 Назад")
async def handle_back_during_removal(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Возвращаемся в меню управления:", reply_markup=manage_sources_menu())

@router.message(lambda message: message.text == "🔙 Назад")
async def handle_back_button(message: Message, state: FSMContext):
    logger.info(f"Пользователь {message.from_user.id} нажал кнопку 'Назад'.")
    await state.clear()
    await message.answer("Возвращаемся в главное меню:", reply_markup=main_menu())

@router.message(lambda message: message.text == "➖ Удалить источник")
async def handle_remove_source_button(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    user_sources = await get_user_sources_for_user(user_id)
    
    if not user_sources:
        await message.answer("❌ У вас нет пользовательских источников.")
        return

    await state.set_state(SourceForm.waiting_source_to_remove)
    await message.answer("Выберите источник для удаления:", 
                        reply_markup=await user_sources_menu(user_id))  # Используем существующее меню
    
# Обработчик удаления источника (должен быть ПЕРВЫМ)
@router.message(StateFilter(SourceForm.waiting_source_to_remove))
async def handle_source_removal(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    source_name = message.text
    result = await remove_user_source(user_id, source_name)

    await state.clear()
    await message.answer(result, reply_markup=manage_sources_menu())


@router.message(StateFilter(SourceForm.waiting_for_source_name))
async def handle_source_name_input(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    logger.info(f"Пользователь {user_id} ввел название источника: {message.text}")
    await state.update_data(source_name=message.text)
    await state.set_state(SourceForm.waiting_for_source_url)
    await message.answer("Теперь отправьте ссылку на RSS-ленту:")


@router.message(StateFilter(SourceForm.waiting_for_source_url), is_http_url)
async def handle_source_url_input(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    logger.info(f"Пользователь {user_id} ввел ссылку: {message.text}")
    data = await state.get_data()
    source_name = data.get("source_name")
    url = message.text
    result = await add_user_source(user_id, source_name, url)
    await state.clear()
    await message.answer(result, reply_markup=await sources_menu(user_id))
    await message.answer(result, reply_markup=main_menu())

@router.message(lambda message: message.text == "📋 Мои источники")
async def handle_show_user_sources_button(message: Message):
    user_id = str(message.from_user.id)
    user_sources = await get_user_sources_for_user(user_id)
    
    if not user_sources:
        await message.answer("📭 У вас пока нет своих источников.")
        return
    
    text = "📋 Ваши источники:\n" + "\n".join(
        [f"• {name} ({url})" for name, url in user_sources.items()]
    )
    await message.answer(text)

async def _is_user_source_message(message: Message) -> bool:
    sources = await get_user_sources(str(message.from_user.id))
    return message.text in sources


@router.message(_is_user_source_message)
async def handle_send_source_news(message: Message):
    user_id = str(message.from_user.id)
    source = message.text
    logger.info(f"Пользователь {user_id} запросил новости из источника: {source}.")
    
    news_list = await get_latest_news(user_id, source)
    
    await _send_news_batch(message, user_id, news_list, f"📰 {source}", "source")

@router.message(lambda message: message.text in NEWS_CATEGORIES)
async def handle_send_category_news(message: Message):
    user_id = str(message.from_user.id)
    category = message.text
    logger.info(f"Пользователь {user_id} запросил новости из категории: {category}.")
    
    news_list = await get_latest_news(user_id, category, is_category=True)
    
    await _send_news_batch(message, user_id, news_list, f"📂 {category}", "category")


@router.callback_query(lambda c: c.data and c.data.startswith("news:"))
async def handle_news_pagination(callback: CallbackQuery):
    _, action, session_id, page_str = callback.data.split(":")
    session = news_sessions.get(session_id)

    if not session or str(callback.from_user.id) != session["user_id"]:
        await callback.answer("Сессия устарела", show_alert=True)
        return

    page = int(page_str)
    total_items = len(session["items"])

    if action == "hide":
        await callback.message.delete()
        await callback.answer("Скрыто")
        return

    if action == "switch":
        origin = session.get("origin")
        if origin == "source":
            await callback.message.answer("Выбери источник:", reply_markup=await sources_menu(session["user_id"]))
        elif origin == "category":
            await callback.message.answer("Выбери категорию:", reply_markup=categories_menu())
        else:
            await callback.message.answer("Выбери действие:", reply_markup=main_menu())
        await callback.answer()
        return

    start = page * NEWS_BATCH_SIZE
    end = start + NEWS_BATCH_SIZE
    batch = session["items"][start:end]

    if not batch:
        await callback.answer("Больше новостей нет")
        return

    text = format_news_batch(batch, start_index=start + 1, title=session["title"])
    keyboard = _build_news_keyboard(session_id, page=page, total_items=total_items)
    await callback.message.edit_text(text, parse_mode="HTML", disable_web_page_preview=True, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("prefs:"))
async def handle_feed_preferences(callback: CallbackQuery):
    action = callback.data.split(":", 1)[1]
    chat_id = str(callback.message.chat.id)
    current = await get_preferences(chat_id)

    if action == "toggle_delivery":
        new_mode = "digest" if current["delivery_mode"] == "stream" else "stream"
        await update_preferences(chat_id, delivery_mode=new_mode)
    elif action == "cycle_max":
        next_value = current["max_items_per_push"] + 1
        if next_value > 10:
            next_value = 1
        await update_preferences(chat_id, max_items_per_push=next_value)
    elif action == "toggle_top":
        await update_preferences(chat_id, only_top_news=not current["only_top_news"])
    elif action == "quiet_start":
        await update_preferences(chat_id, quiet_hours_start=current["quiet_hours"]["start"] + 1)
    elif action == "quiet_end":
        await update_preferences(chat_id, quiet_hours_end=current["quiet_hours"]["end"] + 1)

    updated = await get_preferences(chat_id)
    await callback.message.edit_reply_markup(reply_markup=feed_settings_menu(updated))
    await callback.answer("Сохранено")


@router.message()
async def handle_custom_source(message: Message):
    user_id = str(message.from_user.id)
    logger.info(f"Пользователь {user_id} отправил сообщение: {message.text}")
    # Если сообщение совпадает с кнопками → пропускаем обработку
    if message.text in ["📰 Новости по источнику", "📂 Новости по категории", "🎲 Рандомные новости", "➕ Добавить источник", "🔙 Назад"]:
        return
    
    # Если сообщение не обработано другими обработчиками
    await message.answer("Не понимаю команду 😢")
    if user_states.get(user_id) == "waiting_source_to_remove":
        source_name = message.text
        result = await remove_user_source(user_id, source_name)
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
        result = await add_user_source(user_id, source_name, url)

        if "✅" in result:
            del user_states[user_id]  # Удаляем состояние только при успешном добавлении
            await message.answer(result, reply_markup=await sources_menu(user_id))
        else:
            await message.answer(result, reply_markup=main_menu())
    
    else:
        # Если сообщение не обработано другими обработчиками
        await message.answer("Не понимаю команду 😢")


@router.chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER))
async def on_bot_added_to_group(event: ChatMemberUpdated):
    """Обработчик добавления бота в группу"""
    chat_id = str(event.chat.id)
    await add_bot_group(chat_id)
    logger.info(f"Бот добавлен в группу {chat_id}")

@router.chat_member(ChatMemberUpdatedFilter(IS_MEMBER >> IS_NOT_MEMBER))
async def on_bot_removed_from_group(event: ChatMemberUpdated):
    """Обработчик удаления бота из группы"""
    chat_id = str(event.chat.id)
    await remove_bot_group(chat_id)
    logger.info(f"Бот удален из группы {chat_id}")
