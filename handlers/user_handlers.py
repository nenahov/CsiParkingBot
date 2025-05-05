import asyncio
import random
import re
from datetime import timedelta, datetime, date

from aiogram import Router, F
from aiogram.filters import Command, or_f
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.formatting import Text, TextLink, Bold, as_marked_section, as_key_value
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from config import constants
from handlers.driver_callback import MyCallback, add_button
from models.driver import Driver
from models.parking_spot import SpotStatus
from models.user_audit import UserActionType
from services.audit_service import AuditService
from services.driver_service import DriverService
from services.notification_sender import NotificationSender, EventType, send_alarm, send_reply
from services.param_service import ParamService
from services.parking_service import ParkingService
from services.queue_service import QueueService
from services.reservation_service import ReservationService

router = Router()


@router.message(or_f(Command("status"), F.text.regexp(r"(?i)(.*мой статус)|(.*пока.* статус)")),
                flags={"check_driver": True})
async def show_status(message: Message, session: AsyncSession, driver: Driver, current_day, is_private):
    content, builder = await get_status_message(driver, is_private, session, current_day)
    await message.answer(**content.as_kwargs(), reply_markup=builder.as_markup())


@router.callback_query(MyCallback.filter(F.action == "show-status"),
                       flags={"check_driver": True, "check_callback": True})
async def show_status_callback(callback: CallbackQuery, session, driver, current_day, is_private):
    content, builder = await get_status_message(driver, is_private, session, current_day)
    await callback.message.edit_text(**content.as_kwargs(), reply_markup=builder.as_markup())


async def get_status_message(driver: Driver, is_private, session, current_day):
    await session.commit()
    await session.refresh(driver, ["reservations", "parking_spots", "current_spots"])
    if date.today() != current_day:
        ts = ' завтра'  # tomorrow suffix
        on_ts = ' на завтра'
    else:
        ts = ''
        on_ts = ''
    is_absent = driver.is_absent(current_day)
    occupied_spots = driver.get_occupied_spots()
    spots, reservations = await ParkingService(session).get_spots_with_reservations(current_day)
    in_queue = await QueueService(session).is_driver_in_queue(driver)

    builder = InlineKeyboardBuilder()
    keyboard_sizes = []
    if driver.attributes.get("plus", -1) > -1:
        add_button("🎲 Карма! 🆓", "plus-karma", driver.chat_id, builder)
        keyboard_sizes.append(1)
    if is_absent:
        add_button("🏎️ Вернулся раньше...", "comeback", driver.chat_id, builder)
        keyboard_sizes.append(1)
    else:
        if occupied_spots:
            add_button("🫶 Уехал", "absent", driver.chat_id, builder)
            keyboard_sizes.append(1)
        else:
            add_button(f"🚗 Приеду{ts}...", "comeback", driver.chat_id, builder)
            add_button(f"🫶 Не приеду", "absent", driver.chat_id, builder)
            keyboard_sizes.append(2)
            if not in_queue:
                if not any(res.day_of_week == current_day.weekday() for res in driver.reservations):
                    add_button(f"🙋 Встать в очередь{on_ts}", "join-queue", driver.chat_id, builder)
                    keyboard_sizes.append(1)

        if in_queue:
            add_button(f"✋ Покинуть очередь{on_ts}", "leave-queue", driver.chat_id, builder)
            keyboard_sizes.append(1)

    if is_private:
        add_button("⚙️ Настройки...", "settings", driver.chat_id, builder)
        keyboard_sizes.append(1)
        # В Сб и Вс доберись до парковки
        is_working_day = ((await ParamService(session).get_parameter("current_day_is_working_day", ""))
                          .lower() in ("yes", "true", "t", "1"))
        if not is_working_day:
            builder.add(
                InlineKeyboardButton(text="Игра «Доберись до 🅿️» (-1 💟)", callback_data=f"game_parking"))
            keyboard_sizes.append(1)

    add_button(f"🏆 Мои ачивки...", "achievements", driver.chat_id, builder)
    keyboard_sizes.append(1)
    builder.adjust(*keyboard_sizes)

    content = Text('🪪 ', TextLink(driver.title, url=f"tg://user?id={driver.chat_id}"), "\n",
                   f"{driver.description}", '\n\n')
    if in_queue:
        content += Bold("Вы в очереди") + '\n\n'

    if is_absent:
        content += Bold("Приеду не раньше: ") + driver.absent_until.strftime('%a %d.%m.%Y') + '\n\n'

    if occupied_spots:
        content += Bold("Вы стоите на: 🅿️ ") + ", ".join([str(spot.id) for spot in occupied_spots]) + '\n\n'

    if driver.my_spots():
        content += as_marked_section(
            Bold(f"Закрепленные места на {current_day.strftime('%a %d.%m.%Y')}:"),
            *[as_key_value(f"{spot.id}", f"{await get_spot_info(spot, reservations, session)}")
              for spot in driver.my_spots()],
            marker="• ", )
    else:
        content += Bold("Нет закрепленных мест")

    content += '\n\n'
    content += as_key_value("Карма", driver.get_karma())

    return content, builder


async def get_spot_info(spot, reservations, session):
    # ищем всех в reservations
    if isinstance(reservations, list):
        res_info = reservations
    else:
        res_info = reservations.get(spot.id, [])

    if len(res_info) < 1:
        res = "Свободно"
        res_old = "не было брони"
    else:
        res = "Бронь у " + ', '.join(res.driver.title for res in res_info)
        res_old = "была бронь у " + ', '.join(res.driver.title for res in res_info)

    await session.refresh(spot, ["current_driver"])
    is_woman = spot.current_driver and spot.current_driver.attributes.get("gender", "M") == "F"
    if spot.status == SpotStatus.OCCUPIED:
        return f"Занял{'а' if is_woman else ''} {spot.current_driver.title} ({res_old})"
    elif spot.status == SpotStatus.OCCUPIED_WITHOUT_DEMAND:
        return f"Занял{'а' if is_woman else ''} {spot.current_driver.title}! ({res_old})"
    elif spot.status == SpotStatus.FREE:
        return f"Освободил{'а' if is_woman else ''} {spot.current_driver.title if spot.current_driver else ''} ({res_old})"
    return res


@router.message(
    F.text.regexp(r"(?i).*((уехал.*на|меня не будет|буду отсутствовать) (\d+) (день|дня|дней))").as_("match"),
    flags={"check_driver": True})
async def absent(message: Message, session: AsyncSession, driver: Driver, current_day, is_private, match: re.Match):
    days = int(match.group(3))  # Извлекаем количество дней
    await absent_x_days(days, driver, message, session, current_day, is_private)


@router.message(
    or_f(Command("free"), F.text.regexp(r"(?i).*((не приеду сегодня)|(уже уехал))")), flags={"check_driver": True})
async def absent(message: Message, session: AsyncSession, driver: Driver, current_day, is_private):
    await absent_handler(message, session, driver, current_day, is_private)


@router.message(F.text.regexp(r"(?i).*(не приеду завтра)"), flags={"check_driver": True})
async def absent(message: Message, session: AsyncSession, driver: Driver, current_day, is_private):
    await absent_x_days(2, driver, message, session, current_day, is_private)


@router.callback_query(MyCallback.filter(F.action == "absent"),
                       flags={"check_driver": True, "check_callback": True})
async def absent_callback(callback: CallbackQuery, session, driver, current_day, is_private):
    await absent_handler(callback, session, driver, current_day, is_private)


async def absent_handler(event, session, driver, current_day, is_private):
    is_absent = driver.is_absent(current_day)
    if is_absent:
        if isinstance(event, CallbackQuery):
            await show_status_callback(event, session, driver, current_day, is_private)
        else:
            await event.reply("Вы уже уехали. /status")
        return

    current_week_day = current_day.weekday()  # 0-6 (пн-вс)
    content = Text('🪪 ', TextLink(driver.title, url=f"tg://user?id={driver.chat_id}"), "\n",
                   f"{driver.description}",
                   '\n\n',
                   Bold("На сколько хотите уехать?"))
    builder = InlineKeyboardBuilder()
    add_button("🫶 На сутки", "absent-confirm", driver.chat_id, builder, day_num=1)
    add_button("❤️‍🔥 До конца недели", "absent-confirm", driver.chat_id, builder, day_num=7 - current_week_day)
    builder.add(InlineKeyboardButton(text="🏝️ Буду отсутствовать N дней",
                                     switch_inline_query_current_chat='Меня не будет <ЧИСЛО> дня/дней'))
    add_button("⬅️ Назад", "show-status", driver.chat_id, builder)
    builder.adjust(1)
    await send_reply(event, content, builder)


@router.callback_query(MyCallback.filter(F.action == "absent-confirm"),
                       flags={"check_driver": True, "check_callback": True})
async def absent_confirm_callback(callback: CallbackQuery, callback_data: MyCallback, session, driver, current_day,
                                  is_private):
    await absent_x_days(callback_data.day_num, driver, callback, session, current_day, is_private)


async def absent_x_days(days, driver: Driver, event, session, current_day, is_private=False):
    # прибавим к сегодня N дней и покажем дату
    date = current_day + timedelta(days=days)
    driver.absent_until = date
    await session.refresh(driver, ["current_spots", "parking_spots"])
    current_spots = driver.get_occupied_spots()
    for_queue_after = (datetime.now() +
                       (timedelta(
                           minutes=constants.timeout_before_midnight) if datetime.now().hour >= constants.new_day_begin_hour
                        else timedelta(minutes=constants.timeout_after_midnight)))
    for spot in driver.my_spots():
        spot.for_queue_after = for_queue_after
    await ParkingService(session).leave_spot(driver)
    queue_service = QueueService(session)
    if await queue_service.is_driver_in_queue(driver):
        await queue_service.leave_queue(driver)
        await AuditService(session).log_action(driver.id, UserActionType.LEAVE_QUEUE, current_day,
                                               description=f"{driver.description} покинул очередь, т.к. уехал")
    await send_alarm(event, f"Вы уехали до {date.strftime('%a %d.%m.%Y')}")
    if isinstance(event, CallbackQuery):
        await show_status_callback(event, session, driver, current_day, is_private)

    active_partners = await DriverService(session).get_active_partner_drivers(driver.id, date)
    notification_sender = NotificationSender(event.bot)
    for spot in current_spots:
        await AuditService(session).log_action(driver.id, UserActionType.RELEASE_SPOT, current_day, spot.id,
                                               f"{driver.description} освободил место {spot.id}")
        await session.refresh(spot, ["drivers"])
        for owner in spot.drivers:
            if owner.id != driver.id:
                active_partners.discard(owner)
                if await notification_sender.send_to_driver(EventType.SPOT_RELEASED, driver, owner, spot_id=spot.id):
                    content, builder = await get_status_message(owner, True, session, current_day)
                    await event.bot.send_message(owner.chat_id, **content.as_kwargs(), reply_markup=builder.as_markup())
    for partner in active_partners:
        if await notification_sender.send_to_driver(EventType.PARTNER_ABSENT, driver, partner,
                                                    my_date=date.strftime('%a %d.%m.%Y')):
            content, builder = await get_status_message(partner, True, session, current_day)
            await event.bot.send_message(partner.chat_id, **content.as_kwargs(), reply_markup=builder.as_markup())


@router.message(or_f(Command("book"), F.text.regexp(r"(?i).*((вернулся раньше)|(приеду сегодня))")),
                flags={"check_driver": True})
async def comeback(message: Message, session: AsyncSession, driver: Driver, current_day):
    await comeback_driver(driver, message, session, current_day)


@router.callback_query(MyCallback.filter(F.action == "comeback"),
                       flags={"check_driver": True, "check_callback": True})
async def comeback_callback(callback: CallbackQuery, session: AsyncSession, driver: Driver, current_day):
    await comeback_driver(driver, callback, session, current_day)


async def comeback_driver(driver, event, session, current_day):
    """ Водитель хочет приехать """
    today = current_day
    if driver.is_absent(today):
        driver.absent_until = today
        reservation_service = ReservationService(session)
        await reservation_service.delete_duplicate_reservations(current_day)

    await session.refresh(driver, ["reservations", "parking_spots", "current_spots"])
    occupied_spots = driver.get_occupied_spots()
    builder = InlineKeyboardBuilder()
    content = Text(f"Вы хотите приехать в {current_day.strftime('%a %d.%m.%Y')}\n\n")
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
                Bold(f"Закрепленные места на {current_day.strftime('%a %d.%m.%Y')}:"),
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
                add_button(f"Занять {pref} {spot.id}", "try-occupy-my-spot", driver.chat_id, builder, spot.id)
            sizes = [len(driver.my_spots()), 1]

        # потом вступаем в очередь
        if allow_queue:
            in_queue = await QueueService(session).is_driver_in_queue(driver)
            if in_queue:
                add_button("✋ Покинуть очередь", "leave-queue", driver.chat_id, builder)
            else:
                add_button("🙋 Встать в очередь", "join-queue", driver.chat_id, builder)

    add_button("⬅️ Назад", "show-status", driver.chat_id, builder)
    builder.adjust(*sizes)
    await send_reply(event, content, builder)


@router.callback_query(MyCallback.filter(F.action == "try-occupy-my-spot"),
                       flags={"check_driver": True, "check_callback": True})
async def try_occupy_spot_callback(callback: CallbackQuery, callback_data: MyCallback, session, driver,
                                   current_day, is_private) -> None:
    spot = await ParkingService(session).get_spot_by_id(callback_data.spot_id)
    if spot.status is not None:
        await occupy_spot(callback, callback_data, current_day, driver, is_private, session, check_queue=False)
        return

    reservations = await ReservationService(session).get_spot_reservations(callback_data.spot_id, current_day.weekday())
    if not reservations or any(res.driver.id == driver.id for res in reservations):
        await occupy_spot(callback, callback_data, current_day, driver, is_private, session, check_queue=False)
        return

    content = Bold(f"🚫 Место {callback_data.spot_id} забронировано другим водителем")
    content += "\n\n"
    content += "Вы точно хотите занять его?"
    builder = InlineKeyboardBuilder()
    add_button(f"⚠️ Да, занять место {callback_data.spot_id}", "occupy-my-spot", driver.chat_id, builder,
               callback_data.spot_id)
    add_button("⬅️ Назад", "show-status", driver.chat_id, builder)
    builder.adjust(1)
    await send_reply(callback, content, builder)


@router.callback_query(MyCallback.filter(F.action == "occupy-my-spot"),
                       flags={"check_driver": True, "check_callback": True})
async def occupy_spot_callback(callback: CallbackQuery, callback_data: MyCallback, session, driver,
                               current_day, is_private) -> None:
    await occupy_spot(callback, callback_data, current_day, driver, is_private, session, check_queue=False)


@router.callback_query(MyCallback.filter(F.action == "occupy-spot-from-queue"),
                       flags={"check_driver": True, "check_callback": True})
async def occupy_spot_callback(callback: CallbackQuery, callback_data: MyCallback, session, driver,
                               current_day, is_private) -> None:
    await occupy_spot(callback, callback_data, current_day, driver, is_private, session, check_queue=True)


async def occupy_spot(callback, callback_data, current_day, driver, is_private, session, check_queue):
    parking_service = ParkingService(session)
    spot = await parking_service.get_spot_by_id(callback_data.spot_id)
    await session.refresh(spot, ["current_driver", "drivers"])
    queue_service = QueueService(session)
    if check_queue:
        queue = await queue_service.get_queue_by_driver(driver)
        if not queue or queue.spot_id != callback_data.spot_id:
            await callback.answer("❌ Вы не можете занять это место!", show_alert=True)
            return
    in_queue = await queue_service.is_driver_in_queue(driver)
    if spot.status is not None and not (spot.status == SpotStatus.FREE or spot.current_driver_id == driver.id):
        if in_queue:
            await queue_service.leave_queue(driver)
            await queue_service.join_queue(driver)
        await callback.answer(
            f"❌ Место занято: {spot.current_driver.description} {"\n\n Вы все ещё в очереди." if in_queue else ''}",
            show_alert=True)
        return
    await parking_service.occupy_spot(driver, callback_data.spot_id)
    if in_queue:
        await queue_service.leave_queue(driver)
        await AuditService(session).log_action(driver.id, UserActionType.LEAVE_QUEUE, current_day,
                                               description=f"{driver.description} покинул очередь, т.к. занял место {spot.id}")
    await callback.answer(f"Вы заняли место 🅿️ {spot.id}.\n\nНе забудьте его освободить, если уезжаете не поздно 🫶",
                          show_alert=True)
    await AuditService(session).log_action(driver.id, UserActionType.TAKE_SPOT, current_day, spot.id,
                                           f"{driver.description} занял место {spot.id}")
    await show_status_callback(callback, session, driver, current_day, is_private)
    partners = await DriverService(session).get_active_partner_drivers(driver.id, current_day)
    notification_sender = NotificationSender(callback.bot)
    for owner in spot.drivers:
        if owner.id != driver.id:
            partners.discard(owner)
            if await notification_sender.send_to_driver(EventType.SPOT_OCCUPIED, driver, owner, spot_id=spot.id):
                content, builder = await get_status_message(owner, True, session, current_day)
                await callback.bot.send_message(owner.chat_id, **content.as_kwargs(), reply_markup=builder.as_markup())
    for partner in partners:
        if await notification_sender.send_to_driver(EventType.SPOT_OCCUPIED, driver, partner, spot_id=spot.id):
            content, builder = await get_status_message(partner, True, session, current_day)
            await callback.bot.send_message(partner.chat_id, **content.as_kwargs(), reply_markup=builder.as_markup())


@router.callback_query(MyCallback.filter(F.action == "plus-karma"),
                       flags={"check_driver": True, "check_callback": True})
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
        driver.attributes["karma"] = driver.get_karma() + data.dice.value
        await AuditService(session).log_action(driver.id, UserActionType.DRAW_KARMA, current_day, data.dice.value,
                                               f"Розыгрыш кармы для {driver.description}: +{data.dice.value}; стало {driver.attributes["karma"]}")
        await session.commit()
        await callback.answer(f"💟 Вы получили +{data.dice.value} в карму.\n\nЗавтра будет шанс получить еще.",
                              show_alert=True)

    await show_status_callback(callback, session, driver, current_day, is_private)


@router.message(F.text.regexp(r"(?i).*топ (\d+)?.*карм.* нед").as_("match"), flags={"check_driver": True})
async def top_karma_week(message: Message, session: AsyncSession, match: re.Match):
    limit = int(match.group(1) if match.group(1) is not None else 10)
    result = await AuditService(session).get_weekly_karma(limit)
    content = Bold(f"🏆 Топ {len(result)} кармы водителей за неделю:\n")
    for total, description in result:
        content += '\n'
        content += Bold(f"{total}")
        content += f"\t..\t{description}"
    await message.reply(**content.as_kwargs())


@router.message(F.text.regexp(r"(?i).*топ (\d+)?.*карм").as_("match"), flags={"check_driver": True})
async def top_karma(message: Message, session: AsyncSession, match: re.Match):
    limit = int(match.group(1) if match.group(1) is not None else 10)
    drivers = await DriverService(session).get_top_karma_drivers(limit)
    content = Bold(f"🏆 Топ {len(drivers)} кармы водителей:\n")
    for driver in drivers:
        content += '\n'
        content += Bold(f"{driver.get_karma()}")
        content += f"\t..\t{driver.title}"
    await message.reply(**content.as_kwargs())


@router.message(F.text.regexp(r"(?i).*инфо.*мест.* (\d+)").as_("match"), flags={"check_driver": True})
async def check_spot(message: Message, session: AsyncSession, current_day, match: re.Match):
    spot_id = int(match.group(1))  # Извлекаем номер места
    spot = await ParkingService(session).get_spot_by_id(spot_id)
    if not spot:
        await send_reply(message, Text(f"❌ Место {spot_id} не найдено"), InlineKeyboardBuilder())
        return
    reservations = await ReservationService(session).get_spot_reservations(spot_id, current_day.weekday())
    await send_reply(message, Text(await get_spot_info(spot, reservations, session)), InlineKeyboardBuilder())
