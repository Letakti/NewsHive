import asyncio
from aiogram import Bot, Dispatcher
from aiogram import types
from handlers import router
from config import TOKEN
from logger import logger  # Логирование
from parser import send_auto_news
from aiogram.types import BotCommandScopeAllPrivateChats, BotCommand

async def auto_update_news():
    while True:
        logger.info("Автообновление новостей...")
        # Здесь код обновления данных
        await asyncio.sleep(3600)  # Каждый час

async def main():
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
    await bot.set_my_commands(commands)
    await bot.delete_webhook(drop_pending_updates=True)

    asyncio.create_task(send_auto_news(bot))
    
    try:
        logger.info("🔹 Бот запущен.")
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"❌ Ошибка в работе бота: {e}", exc_info=True)
    finally:
        await bot.session.close()
        logger.info("✅ Бот успешно завершил работу.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.warning("❌ Бот принудительно завершен.")
