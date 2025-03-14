from typing import Any

from aiogram import Router, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message

from config.database import async_session_maker
from handlers.handlers_functions import HandlerFunctions
from handlers.map_handlers import map_command
from handlers.user_handler import show_status
from services.driver_service import DriverService

router = Router()


async def k1(message, k):
    print(k)
    await message.answer(f'k1({k})')


text_handlers = HandlerFunctions()
# text_handlers.add_handler(r"(отсутствую|не приеду|буду отсутствовать)\s+(\d+)\s+(день|дня|дней)",
#                           lambda message, match, session, driver: k1(message, match))
text_handlers.add_handler(r"(/map)|(показать карту)|(карта парковки)",
                          lambda message, match, session, driver: map_command(message))
text_handlers.add_handler(r"(/status)|(мой статус)|(пока.* статус)",
                          lambda message, match, session, driver: show_status(message, session, driver))
text_handlers.add_handler(r"(/help)|(доступные команды)|(помощь по боту)",
                          lambda message, match, session, driver: help_command(message))


@router.message(F.new_chat_members)
async def somebody_added(message: Message):
    async with async_session_maker() as session:
        driver_service = DriverService(session)
        for user in message.new_chat_members:
            # проперти full_name берёт сразу имя И фамилию
            # (на скриншоте выше у юзеров нет фамилии)
            await message.reply(f"Привет, {user.full_name}")
            # Получаем данные пользователя
            driver = await driver_service.get_by_chat_id(user.id)

            title = f'{user.full_name}'
            desc = f'{user.full_name}'

            if not driver:
                await driver_service.register_driver(user.id, user.username, title, desc)

            if not driver or not driver.enabled:
                await message.answer(
                    f"{user.first_name}, обратитесь к администратору для регистрации в системе.")


@router.message(Command("start"))
async def start_command(message: Message):
    await message.answer("Привет, я бот для бронирования парковочных мест!")

    async with async_session_maker() as session:
        # Получаем данные пользователя
        driver_service = DriverService(session)
        driver = await driver_service.get_by_chat_id(message.from_user.id)

        title = f'{message.from_user.full_name}'
        desc = f'{message.from_user.full_name}'

        if not driver:
            await driver_service.register_driver(message.from_user.id, message.from_user.username, title, desc)

        if not driver or not driver.enabled:
            await message.answer(
                f"{message.from_user.first_name}, обратитесь к администратору для регистрации в системе.")

        if message.chat.type == 'group':
            members_count = await message.bot.get_chat_member_count(message.chat.id)
            print(f"В группе {members_count} участников")
            # members_list = [member.user.full_name for member in members]
            # await message.answer("\n".join(members_list))
            # await message.answer(f"В группе {members_count} участников")


@router.message(Command("help"))
async def help_command(message: Message):
    answer = (f"Привет, я бот для бронирования парковочных мест!\n"
              f"\n"
              f"Для работы с ботом достаточно написать одну из следующих команд в чат:\n\n"
              f"<b>Команды для просмотра информации:</b>\n\n"
              f"<code>мой статус</code> - показывает информацию о вас и доступные действия\n\n"
              f"<code>показать карту парковки</code> - показывает карту парковки на текущий момент\n\n"
              f"<b>Команды для бронирования места:</b>\n\n"
              f"<code>буду отсутствовать N дней</code> - освобождает свое парковочное место на N дней (отпуск, командировка, больничный, ремонт машины и т.п)\n\n"
              f"<code>вернулся раньше</code> - возобновляет ваше бронирование парковочного места\n\n"
              f"<code>не приеду сегодня</code> - то же самое, что и <code>буду отсутствовать 1 день</code>\n\n"
              f"<code>приеду сегодня</code> - занимаете ранее зарезервированное место или встаете в очередь\n\n"
              f"<b>Команды для работы с очередью:</b>\n\n"
              f"<code>показать очередь</code> - Показать информацию о наличии свободный мест и очереди\n\n"
              f"<code>встать в очередь</code>, <code>свободное место</code>, <code>свободные места</code> - добавляете себя в конец очереди, если еще не в ней\n\n"
              f"\n")
    await message.answer(answer, parse_mode=ParseMode.HTML)


@router.message()
async def message_handler(message: Message) -> Any:
    async with async_session_maker() as session:
        # Получаем данные пользователя
        driver_service = DriverService(session)
        driver = await driver_service.get_by_chat_id(message.from_user.id)

        if not driver or not driver.enabled:
            return

        await text_handlers.call_handler_func_by_text(message, session, driver)
