import re

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.formatting import Text, TextLink, Bold, as_marked_section, as_key_value
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from handlers.driver_callback import add_button, MyCallback
from models.driver import Driver
from models.user_audit import UserActionType
from services.audit_service import AuditService
from services.driver_service import DriverService
from services.notification_sender import EventType, NotificationSender, send_reply
from services.param_service import ParamService
from services.parking_service import ParkingService
from utils.cars_generator import cars_count

router = Router()


@router.message(Command("set_param"), flags={"check_admin": True})
async def set_param_handler(message: Message, param_service: ParamService):
    try:
        _, key, value = message.text.split(maxsplit=2)
        response = await param_service.set_parameter(key, value)
        await message.answer(response)
    except ValueError:
        await message.answer("Формат команды: /set_param <ключ> <значение>")


@router.message(Command("get_param"), flags={"check_admin": True})
async def get_param_handler(message: Message, param_service: ParamService):
    try:
        _, key = message.text.split(maxsplit=1)
        value = await param_service.get_parameter(key)
        await message.answer(f"{key} = {value}" if value else "Параметр не найден")
    except ValueError:
        await message.answer("Формат команды: /get_param <ключ>")


@router.message(Command("list_params"), flags={"check_admin": True})
async def list_params_handler(message: Message, param_service: ParamService):
    params = await param_service.list_parameters()
    response = "\n".join(f"{k}: {v}" for k, v in params.items()) if params else "Нет параметров"
    await message.answer(response)


@router.message(
    F.text.regexp(r"(?i).*начислить.* ([+-]?\d+) .*кармы(.*)").as_("match"),
    flags={"check_admin": True, "check_driver": True})
async def plus_karma(message: Message, session: AsyncSession, driver: Driver, current_day, is_private, match: re.Match):
    if is_private:
        await message.answer("Команда недоступна в личных сообщениях.")
        return
    if not message.reply_to_message:
        await message.answer("Пожалуйста, ответьте на сообщение пользователя, кому хотите начислить карму.")
        return

    karma = int(match.group(1))  # Извлекаем количество добавляемой кармы
    # Получаем id пользователя, на сообщение которого дан ответ
    replied_user_id = message.reply_to_message.from_user.id
    driver_to = await DriverService(session).get_by_chat_id(replied_user_id)
    if driver_to:
        driver_to.attributes["karma"] = driver_to.get_karma() + karma
        await message.answer(
            f"{'💖' if karma >= 0 else '💔'} {driver_to.description} получает {'+' if karma >= 0 else '-'}{karma} кармы.")
        await NotificationSender(message.bot).send_to_driver(EventType.KARMA_CHANGED, driver, driver_to,
                                                             add_message=match.group(2), karma_change=karma)
        await AuditService(session).log_action(driver_to.id, UserActionType.GET_ADMIN_KARMA, current_day, karma,
                                               f"Админ {driver.title} изменил карму {driver_to.title} на {karma} и стало {driver_to.get_karma()}")
    else:
        await message.answer("Пользователь не нашелся в базе данных.")


@router.message(
    F.text.regexp(r"(?i).*список неактивных пользователей").as_("match"),
    flags={"check_admin": True, "check_driver": True})
async def disabled_drivers(message: Message, session: AsyncSession, current_day, match: re.Match):
    drivers = await DriverService(session).get_inactive_drivers()
    if not drivers:
        await message.answer("Неактивных нет в базе данных.")
        return
    response = "\n".join(f"{driver.id} - {driver.description}" for driver in drivers)
    await message.answer(response)


@router.message(
    F.text.regexp(r"(?i).*поиск водителя (.*)").as_("match"),
    flags={"check_admin": True, "check_driver": True})
async def find_driver(message: Message, session: AsyncSession, current_day, match: re.Match):
    text = match.group(1)
    drivers = await DriverService(session).find_by_text(text)
    if not drivers:
        await message.answer("Водители не нашлись в базе данных.")
        return
    if len(drivers) > 1:
        response = "\n".join(f"{driver.id} - {driver.description}" for driver in drivers)
        await message.answer(response)
        return

    content, builder = await get_user_info(current_day, drivers[0], session)
    await message.answer(**content.as_kwargs(), reply_markup=builder.as_markup())


@router.callback_query(MyCallback.filter(F.action == "enable-user"),
                       flags={"check_admin": True, "check_driver": True})
async def enable_user(callback: CallbackQuery, callback_data: MyCallback, session, driver: Driver, current_day):
    user_id = callback_data.spot_id
    enabled = callback_data.day_num
    user = await DriverService(session).get_by_id(user_id)
    if user:
        user.enabled = enabled
        await AuditService(session).log_action(user.id, UserActionType.ENABLED, current_day, num=enabled,
                                               description=f"Админ {driver.title} {'заблокировал' if enabled == 0 else 'разблокировал'} пользователя {user.title}")
        content, builder = await get_user_info(current_day, user, session)
        await send_reply(callback, content, builder)


@router.callback_query(MyCallback.filter(F.action == "extra-cars"),
                       flags={"check_admin": True, "check_driver": True})
async def extra_cars(callback: CallbackQuery, callback_data: MyCallback, session, current_day):
    user_id = callback_data.spot_id
    extra_cars = callback_data.day_num
    user = await DriverService(session).get_by_id(user_id)
    if user:
        if user.attributes.get("extra_cars", 0) == extra_cars:
            return
        user.attributes["extra_cars"] = extra_cars
        if extra_cars <= 0 and user.attributes.get("car_index", 0) > cars_count:
            user.attributes["car_index"] = user.attributes.get("car_index_bkp",
                                                               user.attributes.get("car_index", user.id))
        elif extra_cars > 0:
            user.attributes["car_index_bkp"] = user.attributes.get("car_index", user.id)
        content, builder = await get_user_info(current_day, user, session)
        await send_reply(callback, content, builder)


@router.message(
    F.text.regexp(r"(?i).*добавить место (\d+) для водителя (\d+)").as_("match"),
    flags={"check_admin": True, "check_driver": True})
async def add_spot(message: Message, session: AsyncSession, match: re.Match):
    spot_id = int(match.group(1))
    driver_id = int(match.group(2))
    spot = await ParkingService(session).get_spot_by_id(spot_id)
    driver = await DriverService(session).get_by_id(driver_id)
    if spot and driver:
        await session.refresh(driver, ["parking_spots"])
        if spot in driver.parking_spots:
            await message.answer("Место уже есть в списке мест водителя.")
            return
        driver.parking_spots.append(spot)
        await session.commit()
        await message.answer("Место успешно добавлено в список мест водителя.")
    else:
        await message.answer("Место или водитель не нашлись в базе данных.")


@router.message(
    F.text.regexp(r"(?i).*удалить место (\d+) у водителя (\d+)").as_("match"),
    flags={"check_admin": True, "check_driver": True})
async def remove_spot(message: Message, session: AsyncSession, match: re.Match):
    spot_id = int(match.group(1))
    driver_id = int(match.group(2))
    spot = await ParkingService(session).get_spot_by_id(spot_id)
    driver = await DriverService(session).get_by_id(driver_id)
    if spot and driver:
        await session.refresh(driver, ["parking_spots"])
        if spot not in driver.parking_spots:
            await message.answer("Место не в списке мест водителя.")
            return
        driver.parking_spots.remove(spot)
        await session.commit()
        await message.answer("Место успешно удалено из списка мест водителя.")
    else:
        await message.answer("Место или водитель не нашлись в базе данных.")


async def get_user_info(current_day, user: Driver, session):
    await session.refresh(user, ["reservations", "parking_spots", "current_spots"])
    is_absent = user.is_absent(current_day)
    occupied_spots = user.get_occupied_spots()
    builder = InlineKeyboardBuilder()
    content = Text('🪪 ', TextLink(user.title, url=f"tg://user?id={user.chat_id}"), "\n",
                   f"{user.id} - {user.description}", '\n\n')

    if not user.enabled:
        content += Bold("🚫 Пользователь заблокирован") + '\n\n'
        add_button("✅ Разблокировать", "enable-user", 0, builder, spot_id=user.id, day_num=1)
    else:
        add_button("🚫 Заблокировать!", "enable-user", 0, builder, spot_id=user.id, day_num=0)

    if is_absent:
        content += Bold("Приедет не раньше: ") + user.absent_until.strftime('%a %d.%m.%Y') + '\n\n'
    if occupied_spots:
        content += Bold("Стоит на: 🅿️ ") + ", ".join([str(spot.id) for spot in occupied_spots]) + '\n\n'
    if user.my_spots():
        content += as_marked_section(
            Bold(f"Закрепленные места:"),
            *[f"{spot.id}" for spot in user.my_spots()],
            marker="• ", )
    else:
        content += Bold("Нет закрепленных мест")

    builder.add(InlineKeyboardButton(text="🅿️ Добавить место",
                                     switch_inline_query_current_chat=f"Добавить место N для водителя {user.id}"))
    builder.add(InlineKeyboardButton(text="🅿️ Удалить место",
                                     switch_inline_query_current_chat=f"Удалить место N у водителя {user.id}"))

    if user.attributes.get("p_state"):
        builder.add(InlineKeyboardButton(text="🗺️ Доберись до 🅿️",
                                         switch_inline_query_current_chat=f"Показать Доберись до парковки {user.id}"))

    content += '\n\n'
    content += as_key_value("Машинка", user.attributes.get("car_index", user.id))
    content += '\n'
    content += as_key_value("Backup машинка",
                            user.attributes.get("car_index_bkp", user.attributes.get("car_index", user.id)))
    content += '\n'
    content += as_key_value("Доп. машинки", "выключены" if user.attributes.get("extra_cars", 0) <= 0 else "включены")
    if user.attributes.get("extra_cars", 0) <= 0:
        add_button("🏎️ Включить доп. машинки", "extra-cars", 0, builder, spot_id=user.id, day_num=1)
    else:
        add_button("❌ Выключить доп. машинки", "extra-cars", 0, builder, spot_id=user.id, day_num=0)

    content += '\n\n'
    content += as_key_value("Карма", user.get_karma())

    builder.adjust(1, 2, 1)
    return content, builder
