import re

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from services.driver_service import DriverService
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
    F.text.regexp(r"(?i).*начислить.*(\d+).*карм").as_("match"), flags={"check_admin": True})
async def absent(message: Message, session: AsyncSession, is_private, match: re.Match):
    if message.reply_to_message:
        karma = int(match.group(1))  # Извлекаем количество добавляемой кармы
        # Получаем id пользователя, на сообщение которого дан ответ
        replied_user_id = message.reply_to_message.from_user.id
        driver = await DriverService(session).get_by_chat_id(replied_user_id)
        if driver:
            driver.attributes['karma'] = driver.attributes.get('karma', 0) + karma
            await message.answer(f"{'💖' if karma > 0 else '💔'} {driver.description} получает {karma} кармы.")
        else:
            await message.answer("Пользователь не нашелся в базе данных.")
    else:
        await message.answer("Пожалуйста, ответьте на сообщение пользователя, кому хотите начислить карму.")
