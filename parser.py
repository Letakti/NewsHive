import aiohttp
import feedparser
import random
import html
from datetime import datetime
from config import NEWS_SOURCES, NEWS_CATEGORIES
from aiogram import Bot
import asyncio
from logger import logger
from storage.db import (
    add_user_source as db_add_user_source,
    get_bot_group_ids,
    get_preferences as db_get_preferences,
    get_user_sources_for_user,
    init_db,
    remove_user_source as db_remove_user_source,
    update_preferences as db_update_preferences,
)

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


async def get_preferences(chat_id: str) -> dict:
    await init_db()
    return _normalize_preferences(await db_get_preferences(str(chat_id)))


async def update_preferences(chat_id: str, **updates):
    await init_db()
    payload = {}
    if "quiet_hours_start" in updates:
        payload["quiet_hours_start"] = int(updates["quiet_hours_start"]) % 24
    if "quiet_hours_end" in updates:
        payload["quiet_hours_end"] = int(updates["quiet_hours_end"]) % 24
    for key in {"delivery_mode", "max_items_per_push", "only_top_news"}:
        if key in updates:
            payload[key] = updates[key]

    updated = await db_update_preferences(str(chat_id), **payload)
    return _normalize_preferences(updated)

async def add_user_source(user_id: str, name: str, url: str):
    """Добавляет источник для конкретного пользователя"""
    await init_db()
    if not await db_add_user_source(user_id, name, url):
        return "⚠️ У вас уже есть такой источник!"
    return f"✅ Источник {name} добавлен в вашу коллекцию!"

async def get_random_news(user_id: str):
    """Возвращает 5 случайных новостей"""
    all_sources = await get_user_sources(user_id)
    sources = list(all_sources.values())
    
    tasks = [fetch_feed(url) for url in sources]
    results = await asyncio.gather(*tasks)
    
    all_news = [news for sublist in results for news in sublist if news]
    random_news = random.sample(all_news, min(5, len(all_news)))
    
    return [f"📰 {news['title']}\n🔗 {news['link']}" for news in random_news]

async def get_user_sources(user_id: str):
    """Возвращает все источники пользователя (стандартные + свои)"""
    await init_db()
    user_sources = await get_user_sources_for_user(str(user_id))
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
    
    all_sources = await get_user_sources(user_id)
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
    await init_db()
    while True:
        try:
            group_ids = await get_bot_group_ids()
            
            # Отправляем новость в каждую группу с учетом настроек
            for chat_id in group_ids:
                try:
                    preferences = await get_preferences(chat_id)
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

async def remove_user_source(user_id: str, source_name: str):
    """Удаляет источник пользователя"""
    await init_db()
    if not await db_remove_user_source(user_id, source_name):
        return "❌ Этот источник нельзя удалить (он стандартный или отсутствует)"
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
