import aiohttp
import feedparser
import random
from config import NEWS_SOURCES, NEWS_CATEGORIES, GROUPS_FILE
from aiogram import Bot
import asyncio
from logger import logger
import json
from config import USER_SOURCES_JSON

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


async def send_auto_news(bot: Bot):
    while True:
        try:
            # Получаем топ-новости через сервисный контекст
            news = await get_top_news(user_id="auto_broadcast")
            if not news:
                logger.info("Авторассылка пропущена: список новостей пуст")
                await asyncio.sleep(3600)
                continue
            
            # Читаем ID групп из файла
            with open(GROUPS_FILE, "r") as f:
                group_ids = f.read().splitlines()
            
            # Отправляем новость в каждую группу
            for chat_id in group_ids:
                try:
                    await bot.send_message(chat_id=chat_id, text=news[0])
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
    for idx, news in enumerate(all_news[:limit], 1):
        formatted_news.append(f"{idx}. [{news['title']}]({news['link']})")
    
    return formatted_news if formatted_news else []
