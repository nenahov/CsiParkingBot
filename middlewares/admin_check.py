from typing import Callable, Awaitable, Dict, Any

from aiogram import BaseMiddleware
from aiogram.dispatcher.flags import get_flag
from aiogram.types import TelegramObject

from services.param_service import ParamService


class AdminCheckMiddleware(BaseMiddleware):
    def __init__(self):
        super().__init__()

    async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any],
    ) -> Any:
        """
        Проверяет права администратора, если метод их требует
        """
        need_check_handler = get_flag(data, "check_admin")
        if not need_check_handler:
            return await handler(event, data)

        param_service = data.get("param_service")
        if not param_service:
            session = data["session"]
            param_service = ParamService(session)
            data["param_service"] = param_service

        # Получаем список администраторов
        user_id = event.from_user.id
        admins_string = await param_service.get_parameter("admins", "")
        admins = [item.strip() for item in admins_string.split(',')]
        if not str(user_id) in admins:
            await event.answer(
                text="Функция только для администратора!",
                show_alert=True
            )
            return
        return await handler(event, data)
