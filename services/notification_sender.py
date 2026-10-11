import logging
from enum import Enum as PyEnum

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, CallbackQuery
from aiogram.utils.formatting import Text

from config import constants
from models.driver import Driver
from services.telegram_ui import (
    answer_content,
    answer_rich,
    edit_content,
    edit_rich,
    event_message,
)

logger = logging.getLogger(__name__)


class EventType(PyEnum):
    """
    Перечисление типов уведомлений.
    """
    NEW_DAY = {"text": "🔔 Наступил вечер, завтра новый день {my_date}\n\n"
                       "Время занимать места, делиться ими или вставать в очередь!\n\n"
                       "Также доступна кнопочка кармы 😉",
               "button_text": "Новый день",
               "description": f"Присылается, когда начинается новый день (в {constants.new_day_begin_hour}:00)."}
    NEW_HOLIDAY = {"text": "🔔 Наступил вечер, завтра новый день {my_date}\n\n"
                           "{txt}"
                           "Доступна кнопочка кармы 😉",
                   "button_text": "Новый день (выходной/праздник)",
                   "description": f"Присылается накануне выходного (в {constants.new_day_begin_hour}:00)."}
    SPOT_OCCUPIED = {"text": "🔔 Место {spot_id} занял{suffix} {driver_from.description}",
                     "button_text": "Заняли Ваше место",
                     "description": "Присылается, когда кто-то занял место, закрепленное за Вами."}
    SPOT_RELEASED = {"text": "🔔 Место {spot_id} освободил{suffix} {driver_from.description}",
                     "button_text": "Освободили Ваше место",
                     "description": "Присылается, когда кто-то освободил место, закрепленное за Вами."}
    PARTNER_ABSENT = {"text": "🔔 {driver_from.description} сказал{suffix}, что не приедет до {my_date}",
                      "button_text": "Напарник не приедет",
                      "description": "Присылается, когда напарник сказал, что не приедет. Возможно, ваше место будет свободно в эти дни и можно его занять."}
    KARMA_CHANGED = {"text": "💟 Ваша карма изменилась на {karma_change}",
                     "button_text": "Изменение кармы",
                     "description": "Присылается, когда администратор изменил Вашу карму."}


async def send_alarm(event, text, *, personal: bool = False):
    if isinstance(event, CallbackQuery):
        await event.answer(text, show_alert=True)
    else:
        await answer_content(event, text, personal=personal)

    logger.info(f"< {text}")


async def send_reply(event, content, builder, *, personal: bool = False):
    if isinstance(event, CallbackQuery):
        await edit_content(
            event,
            content,
            personal=personal,
            reply_markup=builder.as_markup(),
        )
    else:
        await answer_content(
            event,
            content,
            personal=personal,
            reply_markup=builder.as_markup(),
        )
    logger.info(f"< {content.as_markdown()}")


async def send_rich_reply(
        event,
        rich_message,
        builder=None,
        *,
        personal: bool = False,
        fallback_text: str | None = None,
):
    """Отправить/обновить rich-ответ с поддержкой ephemeral-сообщений."""

    markup = builder.as_markup() if builder is not None else None
    message = event_message(event)
    if isinstance(event, CallbackQuery) and message is not None:
        await edit_rich(
            event,
            rich_message,
            personal=personal,
            fallback_text=fallback_text,
            reply_markup=markup,
        )
    else:
        await answer_rich(
            event,
            rich_message,
            personal=personal,
            fallback_text=fallback_text,
            reply_markup=markup,
        )

class NotificationSender:
    """
    Класс-отправщик уведомлений через бот.
    """

    def __init__(self, bot: Bot):
        self.bot = bot

    async def send_to_driver(self, event_type: EventType, /,
                             driver_from: Driver,
                             driver_to: Driver,
                             *, add_message=None,
                             spot_id: int = 0,
                             karma_change: int = 0,
                             my_date: str = None,
                             txt: str = None,
                             keyboard: InlineKeyboardMarkup = None) -> bool:
        """Отправка уведомления водителю с опциональной клавиатурой."""
        # Проверка наличия разрешения на принятие данного типа уведомления от бота у водителя driver_to
        disabled_events = driver_to.attributes.get("disabled_events", [])
        if not driver_to.enabled or event_type.name in disabled_events:
            return False
        is_woman = driver_from.attributes.get("gender", "M") == "F"
        suffix = "а" if is_woman else ""
        message = Text()
        message += event_type.value["text"].format(spot_id=spot_id, driver_from=driver_from, driver_to=driver_to,
                                                   karma_change=karma_change, suffix=suffix, my_date=my_date, txt=txt)
        if add_message is not None and add_message != "":
            message += "\n\n"
            message += add_message
        logger.info(f"{driver_from.title} -> {driver_to.title}: {message.as_markdown()}")
        try:
            await self.bot.send_message(chat_id=driver_to.chat_id, **message.as_kwargs(), reply_markup=keyboard)
            return True
        except Exception as e:
            logger.error(f"Error sending notification to {driver_to.title}: {e}")
            return False
