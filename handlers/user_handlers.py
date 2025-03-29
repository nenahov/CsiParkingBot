import re
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.filters import Command, or_f
from aiogram.types import Message, InlineKeyboardButton, CallbackQuery
from aiogram.utils.formatting import Text, TextLink, Bold, Italic
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from models.driver import Driver
from services.driver_service import DriverService
from services.parking_service import ParkingService
from services.queue_service import QueueService

router = Router()


@router.message(or_f(Command("status"), F.text.regexp(r"(?i)(.*мой статус)|(.*пока.* статус)")),
                flags={"check_driver": True})
async def show_status(message: Message, session: AsyncSession, driver: Driver, current_day, is_private):
    content, builder = await get_status_message(driver, is_private, session, current_day)
    await message.answer(**content.as_kwargs(), reply_markup=builder.as_markup())


async def get_status_message(driver, is_private, session, current_day):
    is_absent = driver.is_absent(current_day)
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
        builder.add(InlineKeyboardButton(text="🚗 Вернулся раньше", callback_data="comeback_" + str(driver.chat_id)))
    else:
        builder.add(InlineKeyboardButton(text="🫶 Не приеду сегодня", callback_data="absent_" + str(driver.chat_id)))
    if is_private:
        builder.add(InlineKeyboardButton(text="📅 Расписание", callback_data='edit_schedule'))
    builder.adjust(1, 2, 1)

    parking_service = ParkingService(session)
    spots, reservations = await parking_service.get_spots_with_reservations(current_day)

    content = Text(TextLink(driver.title, url=f"tg://user?id={driver.chat_id}"), "\n",
                   f"\n"
                   f"{driver.description}\n"
                   f"\n",
                   Bold("Закрепленные места: "),
                   f"{sorted([spot.id for spot in driver.my_spots()])}\n",

                   Bold("Место в очереди: ") if queue_index else '',
                   (str(queue_index) + '\n') if queue_index else '',

                   Bold("Приеду не раньше: ") if is_absent else '',
                   (driver.absent_until.strftime('%d.%m.%Y') + '\n') if is_absent else '',

                   f"\n",
                   Italic("в разработке...\n"),
                   f"\n")
    return content, builder


@router.message(
    F.text.regexp(r"(?i).*((уехал.*на|меня не будет|буду отсутствовать) (\d+) (день|дня|дней))").as_("match"),
    flags={"check_driver": True})
async def absent(message: Message, session: AsyncSession, driver: Driver, current_day, is_private, match: re.Match):
    days = int(match.group(3))  # Извлекаем количество дней
    await absent_x_days(days, driver, message, session, current_day, is_private)


@router.message(
    or_f(Command("free"), F.text.regexp(r"(?i).*((не приеду сегодня)|(уже уехал))")), flags={"check_driver": True})
async def absent(message: Message, session: AsyncSession, driver: Driver, current_day, is_private):
    await absent_x_days(1, driver, message, session, current_day, is_private)


@router.message(F.text.regexp(r"(?i).*(не приеду завтра)"), flags={"check_driver": True})
async def absent(message: Message, session: AsyncSession, driver: Driver, current_day, is_private):
    await absent_x_days(2, driver, message, session, current_day, is_private)


@router.callback_query(F.data.startswith("absent_"), flags={"check_driver": True, "check_callback": True})
async def absent_callback(callback: CallbackQuery, session, driver, current_day, is_private):
    await absent_x_days(1, driver, callback, session, current_day, is_private)


async def absent_x_days(days, driver, event, session, current_day, is_private=False):
    # прибавим к сегодня N дней и покажем дату
    today = datetime.today()
    date = (today + timedelta(days=days)).date()
    driver = await DriverService(session).update_absent_until(driver.id, date)
    await ParkingService(session).leave_spot(driver)
    await QueueService(session).leave_queue(driver)
    if isinstance(event, CallbackQuery):
        await event.answer(f"Вы уехали до {date.strftime('%d.%m.%Y')}", show_alert=True)
    else:
        await event.reply(f"Вы уехали до {date.strftime('%d.%m.%Y')}")
    if isinstance(event, CallbackQuery):
        content, builder = await get_status_message(driver, is_private, session, current_day)
        await event.message.edit_text(**content.as_kwargs(), reply_markup=builder.as_markup())


@router.message(or_f(Command("book"), F.text.regexp(r"(?i).*((вернулся раньше)|(приеду сегодня))")),
                flags={"check_driver": True})
async def comeback(message: Message, session: AsyncSession, driver: Driver, current_day, is_private):
    await comeback_driver(driver, message, session, current_day, is_private)


@router.callback_query(F.data.startswith("comeback_"), flags={"check_driver": True, "check_callback": True})
async def comeback_callback(callback: CallbackQuery, session: AsyncSession, driver: Driver, current_day, is_private):
    await comeback_driver(driver, callback, session, current_day, is_private)


async def comeback_driver(driver, event, session, current_day, is_private=False):
    today = datetime.today().date()
    if driver.is_absent(today):
        driver = await DriverService(session).update_absent_until(driver.id, today)
        if isinstance(event, CallbackQuery):
            await event.answer(f"Ваше резервирование восстановлено", show_alert=True)
        else:
            await event.reply(f"Ваше резервирование восстановлено")

    # await event.reply(f"В разработке... Будет предложение занять одно из ваших мест, либо встать в очередь.")

    if isinstance(event, CallbackQuery):
        content, builder = await get_status_message(driver, is_private, session, current_day)
        await event.message.edit_text(**content.as_kwargs(), reply_markup=builder.as_markup())


async def ttt(message: Message, session: AsyncSession, driver: Driver, is_private):
    # TODO меню для занятия места
    # Определяем список парковок, которые числятся за водителем
    my_spots = driver.my_spots()

    # Также определяем список уже занятых мест этим водителем

    # Также определяем список свободных парковок

    # И количество людей впереди в очереди (если он не в очереди, то длина очереди)
    queue_service = QueueService(session)
    all_queue = await queue_service.get_all()
    queue_index = await queue_service.get_driver_queue_index(driver)
    queue_before_me = queue_index - 1 if queue_index is not None else len(all_queue)
