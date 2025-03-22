from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

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
