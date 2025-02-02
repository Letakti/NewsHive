import aiohttp
import feedparser
import random
from config import NEWS_SOURCES, NEWS_CATEGORIES, GROUPS_FILE
from aiogram import Bot
import asyncio
from logger import logger
import json
from config import USER_SOURCES_JSON
import requests
from requests.exceptions import Timeout

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
                
                return [f"📰 {entry.title}\n🔗 {entry.link}" for entry in feed.entries[:5]]
    except Exception as e:
        logger.error(f"Ошибка при запросе к {url}: {str(e)}")
        return ["⚠️ Не удалось загрузить новости."]

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

def get_random_news(user_id: str):
    """Выбирает 5 случайных новостей из всех источников (общих + пользовательских)"""
    all_news = []
    
    # Получаем ВСЕ источники (общие + пользовательские)
    user_sources = load_user_sources().get(user_id, {})
    combined_sources = {**NEWS_SOURCES, **user_sources}
    
    for source in combined_sources:
        news = get_latest_news(user_id, source)
        all_news.extend(news)
    
    return random.sample(all_news, min(5, len(all_news)))

def get_user_sources(user_id: str):
    """Возвращает все источники пользователя (стандартные + свои)"""
    user_sources = load_user_sources().get(str(user_id), {})
    return {**NEWS_SOURCES, **user_sources}  # Объединяем словари

async def get_latest_news(user_id: str, source: str, is_category: bool = False) -> list:
    """Асинхронно получает новости по источнику"""
    if is_category:
        # Логика для категорий
        sources = NEWS_CATEGORIES.get(source, [])
        if not sources:
            return ["⚠️ В этой категории пока нет источников."]
        
        all_news = []
        for src in sources:
            news = await get_latest_news(user_id, src)  # Рекурсивный вызов для источников
            all_news.extend(news)
        return all_news[:5]
    all_sources = get_user_sources(user_id)
    url = all_sources.get(source)
    
    if not url:
        return ["⚠️ Источник не найден."]
    
    return await fetch_feed(url)



async def send_auto_news(bot: Bot):
    while True:
        try:
            # Получаем случайную новость
            news = get_random_news()
            if not news:
                news = ["📢 Интересных новостей пока нет!"]
            
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

def save_user_sources(data):
    try:
        with open(USER_SOURCES_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Ошибка сохранения источников: {e}")

def remove_user_source(user_id: str, source_name: str):
    """Удаляет источник пользователя"""
    user_sources = load_user_sources()
    
    if user_id not in user_sources or source_name not in user_sources[user_id]:
        return "❌ Этот источник нельзя удалить (он стандартный или отсутствует)"
    
    del user_sources[user_id][source_name]
    save_user_sources(user_sources)
    return f"✅ Источник '{source_name}' удален!"

async def get_top_news(user_id: str, limit: int = 5) -> list:
    """Асинхронно собирает топ-N новостей"""
    sources = get_user_sources(user_id).values()
    
    # Параллельные запросы ко всем источникам
    tasks = [fetch_feed(url) for url in sources]
    results = await asyncio.gather(*tasks)
    
    # Объединяем новости и фильтруем
    all_news = [item for sublist in results for item in sublist if "🔗" in item]
    
    # Форматируем в список
    formatted_news = []
    for idx, news in enumerate(all_news[:limit], 1):
        title, link = news.split("\n🔗 ")
        formatted_news.append(f"{idx}. [{title}]({link})")
    
    return formatted_news if formatted_news else []