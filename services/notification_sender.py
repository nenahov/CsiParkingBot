import logging
from enum import Enum as PyEnum

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, CallbackQuery

from models.driver import Driver

logger = logging.getLogger(__name__)


class EventType(PyEnum):
    """
    Перечисление типов уведомлений.
    """
    SPOT_OCCUPIED = {"text": "Место {spot_id} занял{suffix} {driver_from.description}",
                     "button_text": "Заняли Ваше место",
                     "description": "Присылается, когда кто-то занял место, закрепленное за Вами."}
    SPOT_RELEASED = {"text": "Место {spot_id} освободил{suffix} {driver_from.description}",
                     "button_text": "Освободили Ваше место",
                     "description": "Присылается, когда кто-то освободил место, закрепленное за Вами."}
    PARTNER_ABSENT = {"text": "{driver_from.description} сказал{suffix}, что не приедет до {my_date}",
                      "button_text": "Напарник не приедет",
                      "description": "Присылается, когда напарник сказал, что не приедет. Возможно, ваше место будет свободно в эти дни и можно его занять."}
    KARMA_CHANGED = {"text": "💟 Ваша карма изменилась на {karma_change}",
                     "button_text": "Изменение кармы",
                     "description": "Присылается, когда администратор изменил Вашу карму."}


async def send_alarm(event, text):
    if isinstance(event, CallbackQuery):
        await event.answer(text, show_alert=True)
    else:
        await event.reply(text)


async def send_reply(event, content, builder):
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(**content.as_kwargs(), reply_markup=builder.as_markup())
    else:
        await event.reply(**content.as_kwargs(), reply_markup=builder.as_markup())


class NotificationSender:
    """
    Класс-отправщик уведомлений через бот.
    """

    def __init__(self, bot: Bot):
        self.bot = bot

    async def send_to_driver(self, event_type: EventType,
                             driver_from: Driver, driver_to: Driver,
                             add_message: str = "",
                             spot_id: int = 0, karma_change: int = 0, my_date: str = None,
                             keyboard: InlineKeyboardMarkup = None) -> bool:
        """Отправка уведомления водителю с опциональной клавиатурой."""
        # Проверка наличия разрешения на принятие данного типа уведомления от бота у водителя driver_to
        disabled_events = driver_to.attributes.get("disabled_events", [])
        if not driver_to.enabled or event_type.name in disabled_events:
            return False
        is_woman = driver_from.attributes.get("gender", "M") == "F"
        suffix = "а" if is_woman else ""
        message = event_type.value["text"].format(spot_id=spot_id, driver_from=driver_from, driver_to=driver_to,
                                                  karma_change=karma_change, suffix=suffix, my_date=my_date)
        if add_message is not None and add_message != "":
            message += "\n\n" + add_message
        logger.info(f"{driver_from.title} -> {driver_to.title}: {message}")
        try:
            await self.send_notification(driver_to.chat_id, message, keyboard)
            return True
        except Exception as e:
            logger.error(f"Error sending notification to {driver_to.title}: {e}")
            return False

    async def send_notification(self, user_id: int, message: str, keyboard: InlineKeyboardMarkup = None):
        """Отправка уведомления пользователю с опциональной клавиатурой."""
        await self.bot.send_message(chat_id=user_id, text=message, reply_markup=keyboard)
