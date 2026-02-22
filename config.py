import os

TOKEN = os.getenv("TOKEN")


NEWS_SOURCES = {
    "Lenta.ru (Главное)": "https://lenta.ru/rss/news",  # RSS для главных новостей
    "BBC (Главное)": "http://feeds.bbci.co.uk/news/rss.xml",
    # Остальные источники...
    "Lenta.ru": "https://lenta.ru/rss",
    "BBC": "http://feeds.bbci.co.uk/news/rss.xml",
    "Meduza": "https://meduza.io/rss2/all",
    "IXBT": "https://www.ixbt.com/export/news.rss",
}

NEWS_CATEGORIES = {
    "📌 Основные новости": ["Lenta.ru (Главное)", "BBC (Главное)"],
    "Политика": ["Lenta.ru", "Meduza"],
    "Экономика": ["Lenta.ru"],
    "Спорт": ["Lenta.ru", "BBC"],
    "Технологии": ["IXBT"],
}

CHAT_ID = 123456789  # Укажи свой Telegram ID

DATABASE_URL = os.getenv("DATABASE_URL")
SQLITE_PATH = os.getenv("SQLITE_PATH", "newshive.db")

# Параметры подключения к БД
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
DB_CONNECT_TIMEOUT_SECONDS = float(os.getenv("DB_CONNECT_TIMEOUT_SECONDS", "30"))
DB_BUSY_TIMEOUT_MS = int(os.getenv("DB_BUSY_TIMEOUT_MS", "5000"))

# Интервал автообновления (в секундах)
AUTO_UPDATE_INTERVAL = 6 * 60 * 60  # Каждые 6 часов
