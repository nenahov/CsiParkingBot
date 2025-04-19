from typing import Optional

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton


def add_button(text, action, chat_id, builder,
               spot_id: Optional[int] = None, day_num: Optional[int] = None,
               event_type: Optional[str] = None, bool_value: Optional[bool] = None):
    builder.add(
        InlineKeyboardButton(text=text,
                             callback_data=MyCallback(action=action, user_id=chat_id,
                                                      spot_id=spot_id, day_num=day_num,
                                                      event_type=event_type, bool_value=bool_value).pack()))


class MyCallback(CallbackData, prefix="dcb"):
    action: str
    user_id: int
    spot_id: Optional[int]
    day_num: Optional[int]
    event_type: Optional[str]
    bool_value: Optional[bool]
