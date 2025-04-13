import logging
import os
import random
from datetime import datetime, timedelta

import requests
from aiogram import Router, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.formatting import Bold, Italic

from services.driver_service import DriverService

router = Router()
logger = logging.getLogger(__name__)


@router.message(F.new_chat_members)
async def somebody_added(message: Message, session):
    driver_service = DriverService(session)
    for user in message.new_chat_members:
        # проперти full_name берёт сразу имя И фамилию
        # (на скриншоте выше у юзеров нет фамилии)
        await message.reply(f"Привет, {user.full_name}")
        # Получаем данные пользователя
        driver = await driver_service.get_by_chat_id(user.id)

        if not driver:
            title = f'{user.full_name}'
            desc = f'{user.full_name}'
            driver = await driver_service.register_driver(user.id, user.username, title, desc)

        if not driver.enabled:
            await message.answer(f"{user.first_name}, обратитесь к администратору для регистрации в системе.")


@router.message(Command("start"))
async def start_command(message: Message, session):
    await message.answer(f"Привет, {message.from_user.full_name}, я бот для бронирования парковочных мест!")

    # Получаем данные пользователя
    driver_service = DriverService(session)
    driver = await driver_service.get_by_chat_id(message.from_user.id)

    title = f'{message.from_user.full_name}'
    desc = f'{message.from_user.full_name}'

    if not driver:
        driver = await driver_service.register_driver(message.from_user.id, message.from_user.username, title, desc)

    if not driver or not driver.enabled:
        await message.answer(
            f"{message.from_user.first_name}, обратитесь к администратору для регистрации в системе.")

    driver.attributes["test"] = random.randint(0, 100)

    if message.chat.type == 'group':
        members_count = await message.bot.get_chat_member_count(message.chat.id)
        print(f"В группе {members_count} участников")
        chat_info = await message.bot.get_chat(message.chat.id)
        print(f"{chat_info}")
        # members_list = [member.user.full_name for member in members]
        # await message.answer("\n".join(members_list))
        # await message.answer(f"В группе {members_count} участников")


@router.message(F.text.regexp(r"(?i)(.*написать разработчику)|(.*связаться с разработчиком)"))
async def dev_command(message: Message):
    await message.reply("Передам разработчику")
    await message.bot.send_message(chat_id=203121382,
                                   text=F"Сообщение от [{message.from_user.full_name}](tg://user?id={message.from_user.id}):\n{message.md_text}",
                                   parse_mode=ParseMode.MARKDOWN_V2)


@router.message(F.text.regexp(r"(?i)(.*прогноз.*погод.*завтра)"))
async def show_weather(message: Message):
    day = datetime.now() + timedelta(days=1)
    content = await get_weather_content(day)
    await message.reply(**content.as_kwargs())


@router.message(F.text.regexp(r"(?i)(.*прогноз.*погод)"))
async def show_weather(message: Message):
    day = datetime.now()
    content = await get_weather_content(day)
    await message.reply(**content.as_kwargs())


async def get_weather_content(day):
    API_KEY = os.getenv("OPENWEATHERMAP_API_KEY")
    CITY = "Saint Petersburg,RU"
    BASE_URL = "http://api.openweathermap.org/data/2.5/forecast"
    params = {
        "q": CITY,
        "appid": API_KEY,
        "units": "metric",
        "lang": "ru"
    }
    response = requests.get(BASE_URL, params=params)
    data = response.json()
    logger.debug(f"{data}")
    day_request = day.strftime("%Y-%m-%d")
    weather_map = {
        "01": "☀",
        "02": "⛅️",
        "03": "🌥️",
        "04": "🌥️",
        "09": "🌈",
        "10": "🌧️",
        "11": "⛈️",
        "13": "🌨️",
        "50": "🌫️"
    }
    is_ok = False
    # Фильтрация прогноза на завтра
    content = Bold(f"Погода на {day.strftime('%A %d.%m.%Y')}:")
    for forecast in data["list"]:
        date = forecast["dt_txt"].split()[0]
        if date == day_request:
            is_ok = True
            time = forecast["dt_txt"].split()[1][:5]
            temp = int(forecast["main"]["temp"])
            desc = forecast["weather"][0]["description"]
            icon = forecast["weather"][0]["icon"][:2]
            content += f"\n{time}: \t{temp}°C, \t{weather_map.get(icon, "")} {desc}"
    if not is_ok:
        content += Italic("\nСервис временно недоступен 🤷")
    return content
