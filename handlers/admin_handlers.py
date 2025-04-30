import re

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from models.driver import Driver
from models.user_audit import UserActionType
from services.audit_service import AuditService
from services.driver_service import DriverService
from services.notification_sender import EventType, NotificationSender
from services.param_service import ParamService

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
        driver_to.attributes["karma"] = driver_to.attributes.get("karma", 0) + karma
        await message.answer(
            f"{'💖' if karma >= 0 else '💔'} {driver_to.description} получает {'+' if karma >= 0 else '-'}{karma} кармы.")
        await NotificationSender(message.bot).send_to_driver(EventType.KARMA_CHANGED, driver, driver_to,
                                                             add_message=match.group(2), karma_change=karma)
        await AuditService(session).log_action(driver_to.id, UserActionType.GET_ADMIN_KARMA, current_day, karma,
                                               f"Админ {driver.title} изменил карму {driver_to.title} на {karma} и стало {driver_to.attributes["karma"]}")
    else:
        await message.answer("Пользователь не нашелся в базе данных.")
