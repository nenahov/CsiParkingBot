from enum import Enum as PyEnum

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup

from models.driver import Driver


class EventType(PyEnum):
    """
    Перечисление типов уведомлений.
    """
    SPOT_OCCUPIED = {"text": "Место {spot_id} занял {driver_from.description} /status", "button_text": "Заняли место"}
    SPOT_RELEASED = {"text": "Место {spot_id} освободил {driver_from.description} /status",
                     "button_text": "Освободили место"}
    PARTNER_SAYS_TODAY_SPOT_FREE = {
        "text": "{driver_from.description} сказал, что не приедет и место {spot_id} свободно /status",
        "button_text": "Напарник не приедет"}
    KARMA_CHANGED = {"text": "💟 Ваша карма изменилась на {karma_change}", "button_text": "Изменение кармы"}


class NotificationSender:
    """
    Класс-отправщик уведомлений через бот.
    """

    def __init__(self, bot: Bot):
        self.bot = bot

    async def send_to_driver(self, event_type: EventType, driver_from: Driver, driver_to: Driver, add_message: str,
                             spot_id: int, karma_change: int, keyboard: InlineKeyboardMarkup = None):
        """Отправка уведомления водителю с опциональной клавиатурой."""
        # Проверка наличия разрешения на принятие данного типа уведомления от бота у водителя driver_to
        if not driver_to.attributes.get(event_type.name, True):
            return
        message = event_type.value["text"].format(spot_id=spot_id, driver_from=driver_from, driver_to=driver_to,
                                                  karma_change=karma_change)
        if add_message is not None and add_message != "":
            message += "\n\n" + add_message
        await self.send_notification(driver_to.chat_id, message, keyboard)

    async def send_notification(self, user_id: int, message: str, keyboard: InlineKeyboardMarkup = None):
        """Отправка уведомления пользователю с опциональной клавиатурой."""
        await self.bot.send_message(chat_id=user_id, text=message, reply_markup=keyboard)
