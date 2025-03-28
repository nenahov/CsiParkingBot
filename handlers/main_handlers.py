import random

from aiogram import Router, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message

from services.driver_service import DriverService

router = Router()


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
            await message.answer(
                f"{user.first_name}, обратитесь к администратору для регистрации в системе.")


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

    driver = await driver_service.change_attribute(driver, 'test', str(random.randint(0, 100)))

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
