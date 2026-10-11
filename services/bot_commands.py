"""Команды бота с разными режимами видимости для личных и групповых чатов."""

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeDefault,
)

logger = logging.getLogger(__name__)

PRIVATE_COMMANDS = [
    BotCommand(command="help", description="Помощь"),
    BotCommand(command="status", description="Мой статус"),
    BotCommand(command="map", description="Карта парковки"),
    BotCommand(command="queue", description="Очередь парковки"),
]

GROUP_COMMANDS = [
    # Telegram покажет ответ только инициатору команды, не засоряя общий чат.
    BotCommand(command="status", description="Мой статус", is_ephemeral=True),
    BotCommand(command="help", description="Помощь"),
    BotCommand(command="map", description="Карта парковки"),
    BotCommand(command="queue", description="Очередь парковки"),
]


async def setup_bot_commands(bot: Bot) -> None:
    """Опубликовать актуальное меню команд для личных и групповых чатов."""

    try:
        await bot.set_my_commands(PRIVATE_COMMANDS, scope=BotCommandScopeDefault())
        await bot.set_my_commands(
            PRIVATE_COMMANDS,
            scope=BotCommandScopeAllPrivateChats(),
        )
        await bot.set_my_commands(
            GROUP_COMMANDS,
            scope=BotCommandScopeAllGroupChats(),
        )
    except TelegramBadRequest:
        logger.warning("Не удалось обновить меню команд Telegram", exc_info=True)
