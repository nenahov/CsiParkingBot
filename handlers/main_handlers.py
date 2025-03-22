from aiogram import Router, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.filters import or_f
from aiogram.types import Message
from aiogram.utils.formatting import as_list, as_marked_section, Bold, as_key_value, HashTag, Code, Text

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
        chat_info = await message.bot.get_chat(message.chat.id)
        print(f"{chat_info}")
        # members_list = [member.user.full_name for member in members]
        # await message.answer("\n".join(members_list))
        # await message.answer(f"В группе {members_count} участников")


@router.message(or_f(Command("help", "?"), F.text.regexp(r"(?i)(.*доступные команды)|(.*помощь.* бот)")))
async def help_command(message: Message):
    content = as_list(
        f"Привет, я бот для бронирования парковочных мест!",
        f"Для работы с ботом достаточно написать одну из следующих команд в чат:",
        as_marked_section(
            Bold("Команды для просмотра информации:"),
            as_key_value(Text("ℹ️ ", Code("мой статус")), "показывает информацию о вас и доступные действия"),
            as_key_value(Text("🗺️ ", Code("показать карту парковки")), "показывает карту парковки на текущий момент"),
            as_key_value(Text("🗺️ ", Code("показать карту на завтра")), "показывает карту парковки на завтра"),
            as_key_value(Text("📝 ", Code("все доступные команды")), "показывает это сообщение 😉"),
            marker="• ", ),
        as_marked_section(
            Bold("Команды для бронирования места:"),
            as_key_value(Text("🫶 ", Code("буду отсутствовать N дней")), "освобождает свое парковочное место на N дней"),
            as_key_value(Text("🫶 ", Code("не приеду сегодня")), "то же самое, что и 'буду отсутствовать 1 день'"),
            as_key_value(Text("👋 ", Code("вернулся раньше")), "возобновляет ваше бронирование парковочного места"),
            as_key_value(Text("🚗 ", Code("приеду сегодня")),
                         "занимаете ранее зарезервированное место или встаете в очередь"),
            marker="• ", ),
        as_marked_section(
            Bold("Команды для работы с очередью:"),
            as_key_value(Text("ℹ️ ", Code("показать очередь")),
                         "показывает информацию о наличии свободный мест и очереди"),
            as_key_value(
                Text("🙋 ", Code("свободное место"), ' / ', Code("встать в очередь"), ' / ', Code("приеду сегодня")),
                "добавляете себя в конец очереди, если еще не в ней"),
            as_key_value(Text("✋ ", Code("покинуть очередь"), ' / ', Code("не приеду сегодня")),
                         "удаляете себя из очереди, если находитесь в ней"),
            marker="• ", ),
        as_marked_section(
            Bold("Дополнительно:"),
            as_key_value(Text("✉️ ", Code("написать разработчику <СООБЩЕНИЕ>")),
                         "отправляет сообщение разработчику бота"),
            marker="• ", ),
        HashTag("#commands"),
        sep="\n\n",
    )
    await message.answer(**content.as_kwargs())


@router.message(F.text.regexp(r"(?i)(.*написать разработчику)|(.*связаться с разработчиком)"))
async def dev_command(message: Message):
    await message.reply("Передам разработчику")
    await message.bot.send_message(chat_id=203121382,
                                   text=F"Сообщение от [{message.from_user.full_name}](tg://user?id={message.from_user.id}):\n{message.md_text}",
                                   parse_mode=ParseMode.MARKDOWN_V2)
