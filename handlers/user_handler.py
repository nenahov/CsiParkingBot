from aiogram.enums import ParseMode
from aiogram.types import Message, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.markdown import text
from sqlalchemy.ext.asyncio import AsyncSession

from models.driver import Driver


async def show_status(message: Message, session: AsyncSession, driver: Driver):
    if not driver.enabled:
        await message.answer("Сначала зарегистрируйтесь!")
        return

    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="Не приеду сегодня", switch_inline_query_current_chat='Не приеду сегодня'))
    builder.add(InlineKeyboardButton(text="Покинуть очередь", switch_inline_query_current_chat='Покинуть очередь'))
    builder.add(InlineKeyboardButton(text="Приеду", switch_inline_query_current_chat='Приеду сегодня'))
    builder.add(InlineKeyboardButton(text="Вернулся раньше", switch_inline_query_current_chat='Вернулся раньше'))
    if message.chat.type == 'private':
        builder.add(InlineKeyboardButton(text="📅 Редактировать расписание", callback_data='edit_schedule'))
        builder.add(InlineKeyboardButton(text="👤 Редактировать профиль", callback_data='edit_profile'))
        builder.add(InlineKeyboardButton(text="📝 Помощь", switch_inline_query_current_chat='все доступные команды'))
    builder.adjust(2)

    answer = text(f"[{driver.title}](tg://user?id={message.from_user.id})",
                  f"\n"
                  f"{driver.description}\n"
                  f"\n"
                  f"в разработке\.\.\."
                  f"\n")
    await message.answer(answer, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=builder.as_markup())
