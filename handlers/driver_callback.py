from typing import Optional

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton


def add_button(text, action, chat_id, builder, spot_id: Optional[int] = None, day_of_week: Optional[int] = None):
    builder.add(
        InlineKeyboardButton(text=text, callback_data=MyCallback(action=action, user_id=chat_id, spot_id=spot_id,
                                                                 day_of_week=day_of_week).pack()))


class MyCallback(CallbackData, prefix="dcb"):
    action: str
    user_id: int
    spot_id: Optional[int]
    day_of_week: Optional[int]
