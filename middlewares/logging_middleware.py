import logging

from aiogram import types

# Настройка логирования
logging.basicConfig(
    filename="bot.log",
    filemode="a",
    encoding="utf-8",
    level=logging.INFO,
    format="%(asctime)s\t%(levelname)s\t%(name)s\t%(message)s",
)

logger = logging.getLogger(__name__)


# Middleware
class LoggingMiddleware:
    async def __call__(self, handler, event, data):
        if isinstance(event, types.Message):
            user = event.from_user
            logger.info(f"Message [ID:{event.message_id}] from {user.full_name} [ID:{user.id}]: {event.text}")
        elif isinstance(event, types.CallbackQuery):
            logger.info(f"Callback [ID:{event.id}] from {event.from_user.full_name}: {event.data}")
        elif isinstance(event, types.Poll):
            logger.info(f"Poll: {event.question}")
        elif isinstance(event, types.ChatMemberUpdated):
            logger.info(f"Chat member updated: {event.new_chat_member.status}")
        return await handler(event, data)
