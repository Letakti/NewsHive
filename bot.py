import asyncio
import os
from aiogram import Bot, Dispatcher
from aiogram import types
from handlers import router
from config import TOKEN
from logger import logger  # Логирование
from parser import send_auto_news
from startup_lock import StartupLock

async def auto_update_news():
    while True:
        logger.info("Автообновление новостей...")
        # Здесь код обновления данных
        await asyncio.sleep(3600)  # Каждый час

BOT_USERNAME = "newshiverubot"
LOCK_PATH = os.getenv("POLLING_LOCK_PATH", "/tmp/newshive_polling.lock")


async def main():
    lock = StartupLock(path=LOCK_PATH)
    if not lock.acquire():
        logger.error("❌ Polling lock already acquired. Another bot process is running; exiting.")
        return

    bot = Bot(token=TOKEN)
    dp = Dispatcher()
    
    dp.include_router(router)  # Подключаем обработчики
        # Регистрация команд
    commands = [
        types.BotCommand(command="start", description="Запустить бота"),
        types.BotCommand(command="help", description="Помощь"),
        types.BotCommand(command="top", description="Основные новости"),
        types.BotCommand(command="sources", description="Управление источниками"),
        types.BotCommand(command="news", description="Случайные новости")
    ]
    me = await bot.get_me()
    if (me.username or "").lower() != BOT_USERNAME:
        logger.error(f"❌ Invalid bot token: expected @{BOT_USERNAME}, got @{me.username}. Exiting.")
        await bot.session.close()
        lock.release()
        return

    await bot.set_my_commands(commands)
    logger.info("🔹 Disabling webhook before polling to avoid mixed mode.")
    await bot.delete_webhook(drop_pending_updates=True)

    asyncio.create_task(send_auto_news(bot))
    
    try:
        logger.info("🔹 Бот запущен.")
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"❌ Ошибка в работе бота: {e}", exc_info=True)
    finally:
        await bot.session.close()
        lock.release()
        logger.info("✅ Бот успешно завершил работу.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.warning("❌ Бот принудительно завершен.")
