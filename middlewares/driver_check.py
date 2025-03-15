from typing import Callable, Awaitable, Dict, Any

from aiogram import BaseMiddleware
from aiogram.dispatcher.flags import get_flag
from aiogram.types import TelegramObject

from services.driver_service import DriverService


class DriverCheckMiddleware(BaseMiddleware):
    def __init__(self):
        super().__init__()

    async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any],
    ) -> Any:
        """
        Check whether game is active. This middleware is intended for CallbackQuery only!
        """
        need_check_handler = get_flag(data, "check_driver")
        if not need_check_handler:
            return await handler(event, data)
        session = data["session"]
        # Получаем данные пользователя
        driver_service = DriverService(session)
        driver = await driver_service.get_by_chat_id(event.from_user.id)

        if not driver or not driver.enabled:
            await event.answer(
                text="Сначала зарегистрируйтесь или обратитесь к администратору!",
                show_alert=True
            )
            return
        data["driver"] = driver
        return await handler(event, data)
