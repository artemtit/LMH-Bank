"""Точка входа: инициализация бота, БД и запуск long-polling."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from .config import load_config
from .database import Database
from .handlers import get_router
from .middlewares import DatabaseMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("lmh-bank")


async def _set_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Регистрация и меню"),
            BotCommand(command="menu", description="Главное меню"),
            BotCommand(command="balance", description="Баланс"),
            BotCommand(command="history", description="История операций"),
            BotCommand(command="cards", description="Мои карты"),
            BotCommand(command="help", description="Справка"),
        ]
    )


async def main() -> None:
    config = load_config()

    database = Database(config.db_path)
    await database.connect()
    logger.info("База данных подключена: %s", config.db_path)

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.update.middleware(DatabaseMiddleware(database))
    dp.include_router(get_router())

    await _set_commands(bot)

    try:
        me = await bot.get_me()
        logger.info("Бот запущен: @%s", me.username)
        await dp.start_polling(bot)
    finally:
        await database.close()
        await bot.session.close()
        logger.info("Бот остановлен.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Выход по сигналу пользователя.")
