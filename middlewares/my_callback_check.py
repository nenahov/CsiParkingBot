import logging
import random
from typing import Callable, Awaitable, Dict, Any

from aiogram import BaseMiddleware
from aiogram.dispatcher.flags import get_flag
from aiogram.types import TelegramObject, CallbackQuery

logger = logging.getLogger(__name__)

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
            logger.info(
                f"Пользователь {user_id} ({event.from_user.full_name}) пытался нажать кнопку не для него и получил '{text}'")
            return

        return await handler(event, data)

    async def get_random_restriction_text(self):
        # Список из разных фраз ограничений, говорящих, что нельзя нажимать эту кнопку
        texts = [
            "Вы не можете использовать эту кнопку.",
            "Вы не можете нажать на эту кнопку.",
            "Вы не можете нажать эту кнопку.",
            "❌ Эта кнопка не для вас!",
            "🍊 Это на Новый год! 🎅",
            "Эту кнопку нельзя использовать.",
            "⚡ Не влезай — убьет!",
            "🧀 Эта кнопка — ловушка для любопытных. Ты точно не любопытный?",
            "🏝️ Кнопка в отпуске. Вернётся через ∞ дней.",
            "🍪 Не тыкай! Там живёт тролль, который ест печеньки.",
            "📺 Здесь могла быть ваша реклама. Но кнопка сломалась.",
            "Эта кнопка — как парковка в час пик: трогать нельзя!",
            "🏎️ Не нажимай — иначе твой автомобиль научится дрифтовать без тебя.",
            "🚲 Здесь могла быть твоя парковка, но её уже занял чей-то велосипед.",
            "⚠️ Кнопка на ручнике. Снимите его, но лучше не надо.",
            "Эта кнопка — как парковочное место: кажется свободной, но это не так.",
            "Тыкнешь — твоё место займёт самоуверенный седан с тонировкой.",
            "Осторожно: кнопка вызывает желание парковаться задом как в автошколе.",
            "Эта кнопка — как парковочный конус. Уважай её личное пространство!",
            "✍️ Нажатие = подписание договора о любви к общественному транспорту.",
            "Не тыкай! Кнопка боится, что её заменят на автопилот.",
            "👻 Здесь паркуется призрак сотрудника, который всегда уходит вовремя.",
            "🚬 Кнопка на перекуре.",
            "Кнопка вернётся, когда закончится совещание.",
            "💅 Кнопка на маникюре.",
            "Не нажимай! Иначе твой автомобиль получит повышение вместо тебя.",
            "Кнопка на удалёнке. Вернётся, когда закончатся пробки.",
            "🛠️ Кнопка на техобслуживании.",
            "🛸 Не трогай! Это место зарезервировано для летающих авто из 2050."
        ]

        # Выбираем случайную фразу
        return random.choice(texts)
