import asyncio
import sys
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage

from core.config import settings
from core.database import create_tables
from core.redis import get_redis
from bot.middlewares.db import DbSessionMiddleware
from bot.handlers import start, lesson, review, progress
from services.scheduler.reminders import setup_scheduler, stop_scheduler
from loguru import logger


async def main():
    logger.info("Starting LangBot...")

    # Создаём таблицы (в проде лучше через Alembic)
    await create_tables()

    # Redis storage для FSM
    redis = await get_redis()
    storage = RedisStorage(redis=redis)

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=storage)

    # Middleware
    dp.update.middleware(DbSessionMiddleware())

    # Routers
    dp.include_router(start.router)
    dp.include_router(lesson.router)
    dp.include_router(review.router)
    dp.include_router(progress.router)

    # Scheduler
    setup_scheduler(bot)

    # Graceful shutdown
    async def on_shutdown():
        stop_scheduler()
        await bot.session.close()
        logger.info("Bot stopped")

    try:
        logger.info("Bot polling started")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await on_shutdown()


if __name__ == "__main__":
    asyncio.run(main())
