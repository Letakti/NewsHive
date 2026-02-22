import aiohttp
import feedparser
import random
import html
from datetime import datetime
from config import NEWS_SOURCES, NEWS_CATEGORIES, GROUPS_FILE
from aiogram import Bot
import asyncio
from logger import logger
import json
from config import USER_SOURCES_JSON, USER_PREFERENCES_JSON


DEFAULT_PREFERENCES = {
    "delivery_mode": "stream",
    "max_items_per_push": 3,
    "only_top_news": True,
    "quiet_hours": {"start": 23, "end": 7},
}

async def fetch_feed(url: str) -> list:
    """Асинхронно получает и парсит RSS-ленту"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                content = await response.text()
                feed = feedparser.parse(content)
                
                if feed.get("bozo", 0) != 0:
                    logger.error(f"Ошибка парсинга {url}: {feed.bozo_exception}")
                    return []
                
                return [
                    {
                        "title": entry.title,
                        "link": entry.link,
                        "published": entry.get("published", "")
                    } for entry in feed.entries[:5]
                ]
    except Exception as e:
        logger.error(f"Ошибка при запросе к {url}: {str(e)}")
        return []

def load_user_sources():
    """Загружает источники из JSON-файла"""
    try:
        with open(USER_SOURCES_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_user_sources(data):
    """Сохраняет источники в JSON-файл"""
    with open(USER_SOURCES_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def _normalize_preferences(raw: dict | None) -> dict:
    data = raw or {}
    quiet_hours = data.get("quiet_hours") if isinstance(data.get("quiet_hours"), dict) else {}
    start = quiet_hours.get("start", DEFAULT_PREFERENCES["quiet_hours"]["start"])
    end = quiet_hours.get("end", DEFAULT_PREFERENCES["quiet_hours"]["end"])
    try:
        start = int(start) % 24
        end = int(end) % 24
    except (TypeError, ValueError):
        start = DEFAULT_PREFERENCES["quiet_hours"]["start"]
        end = DEFAULT_PREFERENCES["quiet_hours"]["end"]

    delivery_mode = data.get("delivery_mode")
    if delivery_mode not in {"stream", "digest"}:
        delivery_mode = DEFAULT_PREFERENCES["delivery_mode"]

    max_items = data.get("max_items_per_push", DEFAULT_PREFERENCES["max_items_per_push"])
    try:
        max_items = max(1, min(10, int(max_items)))
    except (TypeError, ValueError):
        max_items = DEFAULT_PREFERENCES["max_items_per_push"]

    return {
        "delivery_mode": delivery_mode,
        "max_items_per_push": max_items,
        "only_top_news": bool(data.get("only_top_news", DEFAULT_PREFERENCES["only_top_news"])),
        "quiet_hours": {"start": start, "end": end},
    }


def load_user_preferences() -> dict:
    try:
        with open(USER_PREFERENCES_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return {}
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_user_preferences(data: dict):
    with open(USER_PREFERENCES_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def get_preferences(chat_id: str) -> dict:
    all_preferences = load_user_preferences()
    return _normalize_preferences(all_preferences.get(str(chat_id)))


def update_preferences(chat_id: str, **updates):
    all_preferences = load_user_preferences()
    current = _normalize_preferences(all_preferences.get(str(chat_id)))

    for key, value in updates.items():
        if key == "quiet_hours_start":
            current["quiet_hours"]["start"] = int(value) % 24
        elif key == "quiet_hours_end":
            current["quiet_hours"]["end"] = int(value) % 24
        elif key in {"delivery_mode", "max_items_per_push", "only_top_news"}:
            current[key] = value

    all_preferences[str(chat_id)] = _normalize_preferences(current)
    save_user_preferences(all_preferences)
    return all_preferences[str(chat_id)]

def add_user_source(user_id: str, name: str, url: str):
    """Добавляет источник для конкретного пользователя"""
    user_sources = load_user_sources()
    
    if user_id not in user_sources:
        user_sources[user_id] = {}
    
    if name in user_sources[user_id]:
        return "⚠️ У вас уже есть такой источник!"
    
    user_sources[user_id][name] = url
    save_user_sources(user_sources)
    return f"✅ Источник {name} добавлен в вашу коллекцию!"

async def get_random_news(user_id: str):
    """Возвращает 5 случайных новостей"""
    all_sources = get_user_sources(user_id)
    sources = list(all_sources.values())
    
    tasks = [fetch_feed(url) for url in sources]
    results = await asyncio.gather(*tasks)
    
    all_news = [news for sublist in results for news in sublist if news]
    random_news = random.sample(all_news, min(5, len(all_news)))
    
    return [f"📰 {news['title']}\n🔗 {news['link']}" for news in random_news]

def get_user_sources(user_id: str):
    """Возвращает все источники пользователя (стандартные + свои)"""
    user_sources = load_user_sources().get(str(user_id), {})
    return {**NEWS_SOURCES, **user_sources}  # Объединяем словари

async def get_latest_news(user_id: str, source: str, is_category: bool = False) -> list:
    """Возвращает новости в виде строк (работает с источниками и категориями)"""
    if is_category:
        sources = NEWS_CATEGORIES.get(source, [])
        if not sources:
            return ["⚠️ В этой категории пока нет источников."]
        
        tasks = [get_latest_news(user_id, src) for src in sources]
        results = await asyncio.gather(*tasks)
        all_news = [item for sublist in results for item in sublist]
        return all_news[:5]
    
    all_sources = get_user_sources(user_id)
    url = all_sources.get(source)
    
    if not url:
        return ["⚠️ Источник не найден."]
    
    news = await fetch_feed(url)
    # Форматируем словари в строки
    return [f"📰 {item['title']}\n🔗 {item['link']}" for item in news] if news else []


async def get_general_news(limit: int = 5) -> list:
    tasks = [fetch_feed(url) for url in NEWS_SOURCES.values()]
    results = await asyncio.gather(*tasks)
    all_news = [item for sublist in results for item in sublist if item]
    random.shuffle(all_news)

    formatted_news = []
    for news in all_news:
        link = news.get("link", "")
        if not link:
            continue
        safe_link = html.escape(link, quote=True)
        title = html.escape(news.get("title", "Без названия"))
        formatted_news.append(f'<a href="{safe_link}">{title}</a>')
        if len(formatted_news) >= limit:
            break
    return formatted_news


def _is_quiet_time(quiet_hours: dict) -> bool:
    now = datetime.now().hour
    start = quiet_hours.get("start", 23)
    end = quiet_hours.get("end", 7)
    if start == end:
        return False
    if start < end:
        return start <= now < end
    return now >= start or now < end


def build_digest_message(news_items: list[str]) -> str:
    body = "\n".join(f"{idx + 1}. {item}" for idx, item in enumerate(news_items))
    return f"🗞 <b>Дайджест новостей</b>\n\n{body}"


async def send_auto_news(bot: Bot):
    while True:
        try:
            # Читаем ID групп из файла
            with open(GROUPS_FILE, "r") as f:
                group_ids = f.read().splitlines()
            
            # Отправляем новость в каждую группу с учетом настроек
            for chat_id in group_ids:
                try:
                    preferences = get_preferences(chat_id)
                    if _is_quiet_time(preferences["quiet_hours"]):
                        logger.info(f"Авторассылка для {chat_id} пропущена: тихие часы")
                        continue

                    limit = preferences["max_items_per_push"]
                    if preferences["only_top_news"]:
                        news = await get_top_news(user_id="auto_broadcast", limit=limit)
                    else:
                        news = await get_general_news(limit=limit)

                    if not news:
                        logger.info(f"Авторассылка пропущена для {chat_id}: список новостей пуст")
                        continue

                    if preferences["delivery_mode"] == "digest":
                        await bot.send_message(
                            chat_id=chat_id,
                            text=build_digest_message(news),
                            parse_mode="HTML",
                            disable_web_page_preview=True,
                        )
                    else:
                        for item in news:
                            await bot.send_message(
                                chat_id=chat_id,
                                text=item,
                                parse_mode="HTML",
                                disable_web_page_preview=True,
                            )
                except Exception as e:
                    logger.error(f"Ошибка отправки в группу {chat_id}: {e}")
        
        except Exception as e:
            logger.error(f"Ошибка в автоотправке: {e}")
        
        # Ждем 1 час
        await asyncio.sleep(3600)

def remove_user_source(user_id: str, source_name: str):
    """Удаляет источник пользователя"""
    user_sources = load_user_sources()
    
    if user_id not in user_sources or source_name not in user_sources[user_id]:
        return "❌ Этот источник нельзя удалить (он стандартный или отсутствует)"
    
    del user_sources[user_id][source_name]
    save_user_sources(user_sources)
    return f"✅ Источник '{source_name}' удален!"

async def get_top_news(user_id: str, limit: int = 5) -> list:
    """Собирает главные новости только из категории 'Основные'"""
    # Получаем источники для категории "Основные новости"
    main_sources = NEWS_CATEGORIES.get("📌 Основные новости", [])
    
    # Параллельно запрашиваем новости из этих источников
    tasks = [fetch_feed(NEWS_SOURCES[source]) for source in main_sources]
    results = await asyncio.gather(*tasks)
    
    all_news = [news for sublist in results for news in sublist if news]
    
    # Форматируем вывод
    formatted_news = []
    for news in all_news[:limit]:
        link = news.get("link", "")
        if not link:
            continue

        safe_link = html.escape(link, quote=True)
        title = html.escape(news.get("title", "Без названия"))
        item_index = len(formatted_news) + 1
        formatted_news.append(f'{item_index}. <a href="{safe_link}">{title}</a>')
    
    return formatted_news if formatted_news else []
