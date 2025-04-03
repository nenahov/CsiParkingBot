from typing import Optional

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton


def add_button(text, action, chat_id, builder, spot_id: Optional[int] = None, day_num: Optional[int] = None):
    builder.add(
        InlineKeyboardButton(text=text, callback_data=MyCallback(action=action, user_id=chat_id, spot_id=spot_id,
                                                                 day_num=day_num).pack()))


class MyCallback(CallbackData, prefix="dcb"):
    action: str
    user_id: int
    spot_id: Optional[int]
    day_num: Optional[int]
