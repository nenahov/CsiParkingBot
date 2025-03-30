import re
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.filters import Command, or_f
from aiogram.types import Message, InlineKeyboardButton, CallbackQuery
from aiogram.utils.formatting import Text, TextLink, Bold, as_marked_section, as_key_value
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from models.driver import Driver
from models.parking_spot import SpotStatus
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

    builder.add(InlineKeyboardButton(text="🚗 Приеду", switch_inline_query_current_chat='Приеду сегодня'))
    if is_absent:
        builder.add(InlineKeyboardButton(text="🚗 Вернулся раньше", callback_data="comeback_" + str(driver.chat_id)))
    else:
        builder.add(InlineKeyboardButton(text="🫶 Не приеду", callback_data="absent_" + str(driver.chat_id)))
        if queue_index is not None:
            builder.add(
                InlineKeyboardButton(text="✋ Покинуть очередь", callback_data="leave-queue_" + str(driver.chat_id)))
        else:
            builder.add(
                InlineKeyboardButton(text="🙋 Встать в очередь", callback_data="join-queue_" + str(driver.chat_id)))
    if driver.attributes.setdefault("plus", -1) > -1:
        builder.add(InlineKeyboardButton(text="🎰 Розыгрыш кармы!",
                                         callback_data='plus-karma_' + str(driver.chat_id)))
    if is_private:
        builder.add(InlineKeyboardButton(text="📅 Расписание", callback_data='edit-schedule'))
    builder.adjust(2, 1)

    parking_service = ParkingService(session)
    spots, reservations = await parking_service.get_spots_with_reservations(current_day)

    spots_info = as_marked_section(
        Bold(f"🅿️ Закрепленные места на {current_day.strftime('%d.%m.%Y')}:"),
        *[as_key_value(f"{spot.id}", f"{await get_spot_info(spot, reservations)}")
          for spot in driver.my_spots()],
        marker="• ", )

    content = Text(TextLink(driver.title, url=f"tg://user?id={driver.chat_id}"), "\n",
                   f"\n"
                   f"{driver.description}"
                   f"\n\n",
                   Bold("Место в очереди: ") if queue_index else '',
                   (str(queue_index) + '\n\n') if queue_index else '',

                   Bold("Приеду не раньше: ") if is_absent else '',
                   (driver.absent_until.strftime('%d.%m.%Y') + '\n\n') if is_absent else '',

                   spots_info,

                   f"\n")
    return content, builder


async def get_spot_info(spot, reservations):
    if spot.status == SpotStatus.OCCUPIED:
        return f"Занято (ID пользователя: {spot.occupied_by})"
    elif spot.status == SpotStatus.OCCUPIED_WITHOUT_DEMAND:
        return f"ЗАНЯТО (ID пользователя: {spot.reserved_by})"
    elif spot.status == SpotStatus.FREE:
        return 'СВОБОДНО'

    # ищем всех в reservations
    res_info = reservations.get(spot.id, [])
    if len(res_info) < 1:
        return 'Свободно'
    return "Резерв у " + ', '.join(res.driver.title for res in res_info)


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
    date = current_day + timedelta(days=days)
    driver.absent_until = date
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
        driver.absent_until = today
        if isinstance(event, CallbackQuery):
            await event.answer(f"Ваше резервирование восстановлено", show_alert=True)
        else:
            await event.reply(f"Ваше резервирование восстановлено")

    # await event.reply(f"В разработке... Будет предложение занять одно из ваших мест, либо встать в очередь.")

    if isinstance(event, CallbackQuery):
        content, builder = await get_status_message(driver, is_private, session, current_day)
        await event.message.edit_text(**content.as_kwargs(), reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("plus-karma_"), flags={"check_driver": True, "check_callback": True})
async def plus_karma_callback(callback: CallbackQuery, session: AsyncSession, driver: Driver, current_day, is_private):
    if driver.attributes.setdefault("plus", -1) < 0:
        await callback.answer("❎ Вы не можете получить больше кармы.\n\nМожет завтра повезет.", show_alert=True)
    elif driver.attributes.setdefault("plus", -1) < 10:
        driver.attributes["plus"] = -1
        await callback.answer("❎ Вам точно повезет в чем-то другом!\n\nПриходите завтра!", show_alert=True)
    else:
        driver.attributes["plus"] = -1
        driver.attributes["karma"] = driver.attributes.setdefault("karma", 0) + 1
        await callback.answer("💟 Вы получили плюсик в карму.\n\nЗавтра будет шанс получить еще.", show_alert=True)

    content, builder = await get_status_message(driver, is_private, session, current_day)
    await callback.message.edit_text(**content.as_kwargs(), reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("leave-queue_"), flags={"check_driver": True, "check_callback": True})
async def leave_queue(callback: CallbackQuery, session: AsyncSession, driver: Driver, current_day, is_private):
    queue_service = QueueService(session)
    queue_index = await queue_service.get_driver_queue_index(driver)
    if queue_index is None:
        await callback.answer("Вы не в очереди", show_alert=True)
    else:
        await queue_service.leave_queue(driver)
        await  callback.answer(f"Вы были в очереди на {queue_index} месте\nТеперь вы не в очереди", show_alert=True)

    content, builder = await get_status_message(driver, is_private, session, current_day)
    await callback.message.edit_text(**content.as_kwargs(), reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("join-queue_"), flags={"check_driver": True, "check_callback": True})
async def join_queue(callback: CallbackQuery, session: AsyncSession, driver: Driver, current_day, is_private):
    queue_service = QueueService(session)
    queue_index = await queue_service.get_driver_queue_index(driver)
    if queue_index is not None:
        await callback.answer(f"Вы уже в очереди на {queue_index} месте", show_alert=True)
    else:
        await queue_service.join_queue(driver)
        queue_index = await queue_service.get_driver_queue_index(driver)
        await callback.answer(f"Вы встали в очередь на {queue_index} место", show_alert=True)
    content, builder = await get_status_message(driver, is_private, session, current_day)
    await callback.message.edit_text(**content.as_kwargs(), reply_markup=builder.as_markup())


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
