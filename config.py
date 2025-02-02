TOKEN = '7152154137:AAHAJ_6JNsl4nEUKRcsYDyMB7ZEaj6OvxqY'


NEWS_SOURCES = {
    "Lenta.ru": "https://lenta.ru/rss",
    "BBC": "http://feeds.bbci.co.uk/news/rss.xml",
    "Meduza": "https://meduza.io/rss2/all",
    "IXBT":"https://www.ixbt.com/export/news.rss"
}

NEWS_CATEGORIES = {
    "Политика": ["Lenta.ru", "Meduza"],
    "Экономика": ["Lenta.ru"],
    "Спорт": ["Lenta.ru", "BBC"],
    "Технологии": ["IXBT"]
}

CHAT_ID = 123456789  # Укажи свой Telegram ID

GROUPS_FILE = "groups.txt"  # Файл для хранения ID групп

# Храним пользовательские источники в файле
USER_SOURCES_JSON = "user_sources.json"

# Интервал автообновления (в секундах)
AUTO_UPDATE_INTERVAL = 6 * 60 * 60  # Каждые 6 часов
