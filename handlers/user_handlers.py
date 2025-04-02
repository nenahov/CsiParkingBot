import asyncio
import random
import re
from datetime import timedelta

from aiogram import Router, F
from aiogram.filters import Command, or_f
from aiogram.types import Message, InlineKeyboardButton, CallbackQuery
from aiogram.utils.formatting import Text, TextLink, Bold, as_marked_section, as_key_value
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from models.driver import Driver
from models.parking_spot import SpotStatus
from services.driver_service import DriverService
from services.parking_service import ParkingService
from services.queue_service import QueueService
from services.reservation_service import ReservationService

router = Router()


@router.message(or_f(Command("status"), F.text.regexp(r"(?i)(.*мой статус)|(.*пока.* статус)")),
                flags={"check_driver": True})
async def show_status(message: Message, session: AsyncSession, driver: Driver, current_day, is_private):
    content, builder = await get_status_message(driver, is_private, session, current_day)
    await message.answer(**content.as_kwargs(), reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("show-status_"), flags={"check_driver": True, "check_callback": True})
async def show_status_callback(callback: CallbackQuery, session, driver, current_day, is_private):
    content, builder = await get_status_message(driver, is_private, session, current_day)
    await callback.message.edit_text(**content.as_kwargs(), reply_markup=builder.as_markup())


async def get_status_message(driver, is_private, session, current_day):
    await session.commit()
    await session.refresh(driver, ["reservations", "parking_spots", "current_spots"])
    is_absent = driver.is_absent(current_day)
    occupied_spots = driver.get_occupied_spots()
    spots, reservations = await ParkingService(session).get_spots_with_reservations(current_day)
    in_queue = await QueueService(session).is_driver_in_queue(driver)

    builder = InlineKeyboardBuilder()
    if is_absent:
        builder.add(InlineKeyboardButton(text="🏎️ Вернулся раньше...", callback_data="comeback_" + str(driver.chat_id)))
    else:
        if occupied_spots:
            builder.add(InlineKeyboardButton(text="🫶 Уехал", callback_data="absent_" + str(driver.chat_id)))
        else:
            builder.add(InlineKeyboardButton(text="🚗 Приеду...", callback_data="book_" + str(driver.chat_id)))
            builder.add(InlineKeyboardButton(text="🫶 Не приеду", callback_data="absent_" + str(driver.chat_id)))
        if in_queue:
            builder.add(
                InlineKeyboardButton(text="✋ Покинуть очередь", callback_data="leave-queue_" + str(driver.chat_id)))
            # А встать в очередь можно только через меню, когда хочешь приехать

    if driver.attributes.get("plus", -1) > -1:
        builder.add(InlineKeyboardButton(text="🎲 Розыгрыш кармы!",
                                         callback_data='plus-karma_' + str(driver.chat_id)))
    if is_private:
        builder.add(InlineKeyboardButton(text="📅 Расписание...", callback_data='edit-schedule'))

    if occupied_spots or is_absent:
        builder.adjust(1)
    else:
        builder.adjust(2, 1)

    content = Text('🪪 ', TextLink(driver.title, url=f"tg://user?id={driver.chat_id}"), "\n",
                   f"{driver.description}", '\n\n')
    if in_queue:
        content += Bold("Вы в очереди") + '\n\n'

    if is_absent:
        content += Bold("Приеду не раньше: ") + driver.absent_until.strftime('%d.%m.%Y') + '\n\n'

    if occupied_spots:
        content += Bold("Вы стоите на: 🅿️ ") + ", ".join([str(spot.id) for spot in occupied_spots]) + '\n\n'

    content += as_marked_section(
        Bold(f"Закрепленные места на {current_day.strftime('%d.%m.%Y')}:"),
        *[as_key_value(f"{spot.id}", f"{await get_spot_info(spot, reservations, session)}")
          for spot in driver.my_spots()],
        marker="• ", ) + '\n\n'

    content += as_key_value("Карма", driver.attributes.get("karma", 0))

    return content, builder


async def get_spot_info(spot, reservations, session):
    # ищем всех в reservations
    res_info = reservations.get(spot.id, [])
    if len(res_info) < 1:
        res = "Нет брони"
    else:
        res = "Бронь у " + ', '.join(res.driver.title for res in res_info)

    current = ''
    if spot.status == SpotStatus.OCCUPIED:
        await session.refresh(spot, ["current_driver"])
        current = f" / Занято ({spot.current_driver.title})"
    elif spot.status == SpotStatus.OCCUPIED_WITHOUT_DEMAND:
        await session.refresh(spot, ["current_driver"])
        current = f" / Занято! ({spot.current_driver.title})"
    elif spot.status == SpotStatus.FREE:
        current = ' / Уже свободно'

    return res + current


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
        await show_status_callback(event, session, driver, current_day, is_private)


@router.message(or_f(Command("book"), F.text.regexp(r"(?i).*((вернулся раньше)|(приеду сегодня))")),
                flags={"check_driver": True})
async def comeback(message: Message, session: AsyncSession, driver: Driver, current_day, is_private):
    await comeback_driver(driver, message, session, current_day, is_private)


@router.callback_query(or_f(F.data.startswith("comeback_"), F.data.startswith("book_")),
                       flags={"check_driver": True, "check_callback": True})
async def comeback_callback(callback: CallbackQuery, session: AsyncSession, driver: Driver, current_day, is_private):
    await comeback_driver(driver, callback, session, current_day, is_private)


async def comeback_driver(driver, event, session, current_day, is_private=False):
    """ Водитель хочет приехать """
    today = current_day
    if driver.is_absent(today):
        driver.absent_until = today
        reservation_service = ReservationService(session)
        await reservation_service.delete_duplicate_reservations(current_day)

    await session.refresh(driver, ["reservations", "parking_spots", "current_spots"])
    occupied_spots = driver.get_occupied_spots()
    builder = InlineKeyboardBuilder()
    content = Text(f"Вы хотите приехать {current_day.strftime('%d.%m.%Y')}\n\n")
    sizes = [1]
    if occupied_spots:
        # сначала ищем в занятых
        content += f"Вы уже занимаете место: 🅿️ {', '.join(str(spot.id) for spot in occupied_spots)}"
    else:
        allow_queue = True
        if driver.my_spots():
            # потом в ваших местах
            spots, reservations = await ParkingService(session).get_spots_with_reservations(current_day)
            content += as_marked_section(
                Bold(f"Закрепленные места на {current_day.strftime('%d.%m.%Y')}:"),
                *[as_key_value(f"{spot.id}", f"{await get_spot_info(spot, reservations, session)}")
                  for spot in driver.my_spots()],
                marker="• ", ) + '\n\n'
            for spot in driver.my_spots():
                pref = "⚪"
                if spot.status == SpotStatus.OCCUPIED or spot.status == SpotStatus.OCCUPIED_WITHOUT_DEMAND:
                    pref = "🔴"
                elif spot.status == SpotStatus.FREE:
                    pref = "⚪"
                else:
                    res_info = reservations.get(spot.id, [])
                    if len(res_info) < 1:
                        pref = "⚪"
                    elif any(res.driver.id == driver.id for res in res_info):
                        pref = "🟢"
                        allow_queue = False
                    else:
                        pref = "🔴"
                builder.add(InlineKeyboardButton(text=f"{pref} {spot.id}",
                                                 callback_data=f"occupy-spot_{str(driver.chat_id)}_{spot.id}"))
            sizes = [len(driver.my_spots()), 1]

        # потом вступаем в очередь
        if allow_queue:
            in_queue = await QueueService(session).is_driver_in_queue(driver)
            if in_queue:
                builder.add(
                    InlineKeyboardButton(text="✋ Покинуть очередь", callback_data="leave-queue_" + str(driver.chat_id)))
            else:
                builder.add(
                    InlineKeyboardButton(text="🙋 Встать в очередь", callback_data="join-queue_" + str(driver.chat_id)))

    builder.add(InlineKeyboardButton(text="⬅️ Назад", callback_data='show-status_' + str(driver.chat_id)))
    builder.adjust(*sizes)
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(**content.as_kwargs(), reply_markup=builder.as_markup())
    else:
        await event.reply(**content.as_kwargs(), reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("occupy-spot_"), flags={"check_driver": True, "check_callback": True})
async def occupy_spot_callback(callback: CallbackQuery, session, driver, current_day, is_private):
    await ParkingService(session).occupy_spot(driver, int(callback.data.split("_")[2]))
    await QueueService(session).leave_queue(driver)
    await show_status_callback(callback, session, driver, current_day, is_private)


@router.callback_query(F.data.startswith("plus-karma_"), flags={"check_driver": True, "check_callback": True})
async def plus_karma_callback(callback: CallbackQuery, session: AsyncSession, driver: Driver, current_day, is_private):
    if driver.attributes.get("plus", -1) < 0:
        await callback.answer("❎ Вы не можете получить больше кармы.\n\nМожет завтра повезет.", show_alert=True)
    else:
        driver.attributes["plus"] = -1
        if not is_private:
            await callback.bot.send_message(chat_id=driver.chat_id, text="Розыгрыш кармы! /status")
        data = await callback.bot.send_dice(chat_id=driver.chat_id, emoji=random.choice(['🎲', '🎯', '🏀', '⚽', '🎳']))
        await session.commit()
        await show_status_callback(callback, session, driver, current_day, is_private)
        await asyncio.sleep(5 if is_private else 13)
        driver.attributes["karma"] = driver.attributes.get("karma", 0) + data.dice.value
        await callback.answer(f"💟 Вы получили +{data.dice.value} в карму.\n\nЗавтра будет шанс получить еще.",
                              show_alert=True)
    await show_status_callback(callback, session, driver, current_day, is_private)


@router.message(F.text.regexp(r"(?i)(.*топ карма)"), flags={"check_driver": True})
async def top_karma(message: Message, session: AsyncSession, driver: Driver, current_day, is_private):
    drivers = await DriverService(session).get_top_karma_drivers(10)
    content = Text(Bold(f"🏆 Топ {len(drivers)} кармы водителей:\n"))
    for driver in drivers:
        content += '\n'
        content += Bold(f"{driver.attributes.get('karma', 0)}")
        content += f"\t..\t{driver.title}"
    await message.reply(**content.as_kwargs())


@router.callback_query(F.data.startswith("leave-queue_"), flags={"check_driver": True, "check_callback": True})
async def leave_queue(callback: CallbackQuery, session: AsyncSession, driver: Driver, current_day, is_private):
    queue_service = QueueService(session)
    in_queue = await queue_service.is_driver_in_queue(driver)
    if not in_queue:
        await callback.answer("Вы не в очереди", show_alert=True)
    else:
        await queue_service.leave_queue(driver)
        await callback.answer(f"Теперь вы не в очереди", show_alert=True)
    await show_status_callback(callback, session, driver, current_day, is_private)


@router.callback_query(F.data.startswith("join-queue_"), flags={"check_driver": True, "check_callback": True})
async def join_queue(callback: CallbackQuery, session: AsyncSession, driver: Driver, current_day, is_private):
    queue_service = QueueService(session)
    in_queue = await queue_service.is_driver_in_queue(driver)
    if in_queue:
        await callback.answer(f"Вы уже в очереди", show_alert=True)
    else:
        # TODO Если уже есть место, которое вы занимаете, то никакой очереди? или можно встать?
        await queue_service.join_queue(driver)
        await callback.answer(f"Вы встали в очередь", show_alert=True)
    await show_status_callback(callback, session, driver, current_day, is_private)
