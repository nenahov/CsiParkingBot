import re
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.filters import Command, or_f
from aiogram.types import Message, InlineKeyboardButton
from aiogram.utils.formatting import Text, TextLink, Bold
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from models.driver import Driver
from services.driver_service import DriverService
from services.queue_service import QueueService

router = Router()


@router.message(or_f(Command("status"), F.text.regexp(r"(?i)(.*мой статус)|(.*пока.* статус)")),
                flags={"check_driver": True})
async def show_status(message: Message, session: AsyncSession, driver: Driver, is_private):
    today = datetime.today().date()
    is_absent = (driver.absent_until is not None) and (driver.absent_until > today)

    queue_service = QueueService(session)
    queue_index = await queue_service.get_driver_queue_index(driver)

    builder = InlineKeyboardBuilder()

    if queue_index is not None:
        builder.add(
            InlineKeyboardButton(text="✋ Покинуть очередь", switch_inline_query_current_chat='Покинуть очередь'))
    else:
        builder.add(
            InlineKeyboardButton(text="🙋 Встать в очередь", switch_inline_query_current_chat='Встать в очередь'))

    builder.add(InlineKeyboardButton(text="🚗 Приеду", switch_inline_query_current_chat='Приеду сегодня'))
    if is_absent:
        builder.add(InlineKeyboardButton(text="🚗 Вернулся раньше", switch_inline_query_current_chat='Вернулся раньше'))
    else:
        builder.add(
            InlineKeyboardButton(text="🫶 Не приеду сегодня", switch_inline_query_current_chat='Не приеду сегодня'))

    if is_private:
        builder.add(InlineKeyboardButton(text="📅 Расписание", callback_data='edit_schedule'))
        builder.add(InlineKeyboardButton(text="👤 Профиль", callback_data='edit_profile'))
        builder.add(InlineKeyboardButton(text="📝 Помощь", switch_inline_query_current_chat='Все доступные команды'))
    builder.adjust(1, 2, 1, 1)

    content = Text(TextLink(driver.title, url=f"tg://user?id={driver.chat_id}"), "\n",
                   f"\n"
                   f"{driver.description}\n"
                   f"\n",

                   Bold("Закрепленные места: "), f"{sorted([p.id for p in driver.parking_spots])}\n",

                   Bold("Место в очереди: ") if queue_index else '',
                   (str(queue_index) + '\n') if queue_index else '',

                   Bold("Приеду не раньше: ") if is_absent else '',
                   (driver.absent_until.strftime('%d.%m.%Y') + '\n') if is_absent else '',

                   f"\n_в разработке_",
                   f"\n")
    await message.answer(**content.as_kwargs(), reply_markup=builder.as_markup())


@router.message(
    F.text.regexp(
        r"(?i).*(((уехал.*на|меня не будет|буду отсутствовать) (\d+) (день|дня|дней))|(не приеду сегодня)|(уже уехал))").as_(
        "match"),
    flags={"check_driver": True})
async def absent(message: Message, session: AsyncSession, driver: Driver, is_private, match: re.Match):
    if match.group(2):  # Проверяем, что сработала часть с "уехал"
        days = int(match.group(4))  # Извлекаем количество дней
    else:  # Сработало "не приеду сегодня"
        days = 1

    # прибавим к сегодня 3 дня и покажем дату
    today = datetime.today()
    date = today + timedelta(days=days)
    await DriverService(session).update_absent_until(driver.id, date)
    await message.reply(f"Вы уехали до {date.strftime('%d.%m.%Y')}")


@router.message(F.text.regexp(r"(?i).*((вернулся раньше)|(приеду сегодня))"),
                flags={"check_driver": True})
async def comeback(message: Message, session: AsyncSession, driver: Driver, is_private):
    today = datetime.today().date()
    if (driver.absent_until is not None) and (driver.absent_until > today):
        await DriverService(session).update_absent_until(driver.id, today)
        await message.reply(f"Ваше резервирование восстановлено")
