from typing import Any

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.formatting import as_list, as_marked_section, Bold, as_key_value, HashTag, Code

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
text_handlers.add_handler(r"(/map)|(пока.* карт(а|у))|(карт(а|у) парковки)",
                          lambda message, match, session, driver: map_command(message, session, driver))
text_handlers.add_handler(r"(/status)|(мой статус)|(пока.* статус)",
                          lambda message, match, session, driver: show_status(message, session, driver))
text_handlers.add_handler(r"(/help)|(/commands)|(доступные команды)|(помощь по боту)",
                          lambda message, match, session, driver: help_command(message))


@router.message(F.new_chat_members)
async def somebody_added(message: Message, session):
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
async def start_command(message: Message, session):
    await message.answer(f"Привет, {message.from_user.full_name}, я бот для бронирования парковочных мест!")

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
    content = as_list(
        f"Привет, я бот для бронирования парковочных мест!",
        f"Для работы с ботом достаточно написать одну из следующих команд в чат:",
        as_marked_section(
            Bold("Команды для просмотра информации:"),
            as_key_value(Code("ℹ️ мой статус"), "показывает информацию о вас и доступные действия"),
            as_key_value(Code("🗺️ показать карту парковки"), "показывает карту парковки на текущий момент"),
            marker="• ", ),
        as_marked_section(
            Bold("Команды для бронирования места:"),
            as_key_value(Code("🫶 буду отсутствовать N дней"), "освобождает свое парковочное место на N дней"),
            as_key_value(Code("🫶 не приеду сегодня"), "то же самое, что и 'буду отсутствовать 1 день'"),
            as_key_value(Code("👋 вернулся раньше"), "возобновляет ваше бронирование парковочного места"),
            as_key_value(Code("🚗 приеду сегодня"), "занимаете ранее зарезервированное место или встаете в очередь"),
            marker="• ", ),
        as_marked_section(
            Bold("Команды для работы с очередью:"),
            as_key_value(Code("ℹ️ показать очередь"), "показывает информацию о наличии свободный мест и очереди"),
            as_key_value(Code("🙋 свободное место") + ', ' + Code("встать в очередь"),
                         "добавляете себя в конец очереди, если еще не в ней"),
            marker="• ", ),
        HashTag("#commands"),
        sep="\n\n",
    )
    await message.answer(**content.as_kwargs())


@router.message()
async def message_handler(message: Message, session) -> Any:
    # Получаем данные пользователя
    driver_service = DriverService(session)
    driver = await driver_service.get_by_chat_id(message.from_user.id)

    if not driver or not driver.enabled:
        return

    await text_handlers.call_handler_func_by_text(message, session, driver)
