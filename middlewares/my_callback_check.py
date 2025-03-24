import random
from typing import Callable, Awaitable, Dict, Any

from aiogram import BaseMiddleware
from aiogram.dispatcher.flags import get_flag
from aiogram.types import TelegramObject, CallbackQuery


class MyCallbackCheckMiddleware(BaseMiddleware):
    def __init__(self):
        super().__init__()

    async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any],
    ) -> Any:
        """
        Для некоторых callback-ов необходимо проверить, что это тот самый пользователь, для которого были кнопки
        """

        if not isinstance(event, CallbackQuery):
            return await handler(event, data)

        need_check_handler = get_flag(data, "check_callback")
        if not need_check_handler:
            return await handler(event, data)

        # Проверяем первую часть data из колбека и сравниваем ее с id пользователя
        user_id = event.from_user.id
        callback_data = (event.data + "_").split("_")[1]
        if str(user_id) != callback_data:
            text = await self.get_random_restriction_text()
            await event.answer(text=text, show_alert=True)
            print(
                f"Пользователь {user_id} ({event.from_user.full_name}) пытался нажать кнопку не для него и получил '{text}'")
            return

        return await handler(event, data)

    async def get_random_restriction_text(self):
        # Список из разных фраз ограничений, говорящих, что нельзя нажимать эту кнопку
        texts = [
            "Вы не можете использовать эту кнопку",
            "Вы не можете нажать на эту кнопку",
            "Вы не можете нажать эту кнопку",
            "Эта кнопка не для вас",
            "Это на Новый год 🎅",
            "Эту кнопку нельзя использовать",
            "Не влезай - убьет ⚡"
        ]

        # Выбираем случайную фразу
        return random.choice(texts)
