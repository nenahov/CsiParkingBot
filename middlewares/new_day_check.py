import logging
from typing import Callable, Awaitable, Dict, Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from services.param_service import ParamService
from utils.new_day_checker import check_current_day

logger = logging.getLogger(__name__)


class NewDayCheckMiddleware(BaseMiddleware):
    def __init__(self):
        super().__init__()

    async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any],
    ) -> Any:
        """
        Проверяет, наступило ли время обнулить очередь и состояние парковки
        """
        param_service = data.get("param_service")
        if not param_service:
            session = data["session"]
            param_service = ParamService(session)
            data["param_service"] = param_service

        current_day = await check_current_day(event.bot, data["session"], param_service)
        data["current_day"] = current_day

        return await handler(event, data)
