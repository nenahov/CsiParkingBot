from aiogram import Router, F
from aiogram.filters import Command
from aiogram.filters import or_f
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.formatting import as_list, as_marked_section, Bold, as_key_value, HashTag, Code, Text
from aiogram.utils.keyboard import InlineKeyboardBuilder

router = Router()


@router.message(or_f(Command("help", "?", "commands"),
                     F.text.regexp(r"(?i)(.*доступные команды)|(.*помощь.* бот)|(.*список.* команд)")))
async def help_command(message: Message):
    await main_commands(message, True)


@router.callback_query(F.data.startswith("back_to_main"))
async def back_to_main(callback: CallbackQuery):
    await main_commands(callback.message, False)


async def main_commands(message, is_new: bool):
    content = as_list(
        f"Привет, я бот для бронирования парковочных мест!",
        f"Для работы с ботом достаточно написать ему в чат.",
        HashTag("#commands"),
        sep="\n\n",
    )
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="ℹ️ Информация", callback_data=f"info_commands"))
    builder.add(InlineKeyboardButton(text="🫶 Резервирование места", callback_data=f"reservation_commands"))
    builder.add(InlineKeyboardButton(text="🙋 Очередь на парковку", callback_data=f"queue_commands"))
    builder.add(InlineKeyboardButton(text="🤖 Другое", callback_data=f"other_commands"))
    builder.adjust(1)
    if is_new:
        await message.answer(**content.as_kwargs(), reply_markup=builder.as_markup())
    else:
        await message.edit_text(**content.as_kwargs(), reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("info_commands"))
async def info_commands(callback: CallbackQuery):
    """Обработчик показа информационных команд"""
    content = await get_content_text(
        as_marked_section(
            Bold("Команды для просмотра информации:"),
            as_key_value(Text("ℹ️ ", Code("мой статус")), "показывает информацию о вас и доступные действия"),
            as_key_value(Text("🗺️ ", Code("показать карту парковки")), "показывает карту парковки на текущий момент"),
            as_key_value(Text("🗺️ ", Code("показать карту на завтра")), "показывает карту парковки на завтра"),
            as_key_value(Text("📝 ", Code("показать список команд")), "показывает список команд"),
            marker="• ", ))
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="ℹ️ Мой статус", switch_inline_query_current_chat='Мой статус'))
    builder.add(InlineKeyboardButton(text="🗺️ Показать карту", switch_inline_query_current_chat='Показать карту'))
    builder.add(InlineKeyboardButton(text="🗺️ Карта на завтра",
                                     switch_inline_query_current_chat='Показать карту на завтра'))
    builder.add(InlineKeyboardButton(text="📝 Показать список команд", switch_inline_query_current_chat='Список команд'))
    builder.add(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"back_to_main"))
    builder.adjust(1, 2, 1, 1)
    await callback.message.edit_text(**content.as_kwargs(), reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("reservation_commands"))
async def reservation_commands(callback: CallbackQuery):
    """Обработчик показа команд бронирования места"""
    content = await get_content_text(
        as_marked_section(
            Bold("Команды для бронирования места:"),
            as_key_value(Text("🫶 ", Code("буду отсутствовать N дней")), "освобождает свое парковочное место на N дней"),
            as_key_value(Text("🫶 ", Code("не приеду сегодня")), "то же самое, что и 'буду отсутствовать 1 день'"),
            as_key_value(Text("🏎️ ", Code("вернулся раньше")), "возобновляет ваше бронирование парковочного места"),
            as_key_value(Text("🚗 ", Code("приеду сегодня")),
                         "занимаете ранее зарезервированное место или встаете в очередь"),
            marker="• ", ))
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="🚗 Приеду сегодня", switch_inline_query_current_chat='Приеду сегодня'))
    builder.add(InlineKeyboardButton(text="🫶 Не приеду сегодня", switch_inline_query_current_chat='Не приеду сегодня'))
    builder.add(InlineKeyboardButton(text="🏝️ Буду отсутствовать N дней",
                                     switch_inline_query_current_chat='Меня не будет <ЧИСЛО> дня/дней'))
    builder.add(InlineKeyboardButton(text="🏎️ Вернулся раньше", switch_inline_query_current_chat='Вернулся раньше'))
    builder.add(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"back_to_main"))
    builder.adjust(1)
    await callback.message.edit_text(**content.as_kwargs(), reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("queue_commands"))
async def queue_commands(callback: CallbackQuery):
    """Обработчик показа команд для работы с очередью"""
    content = await get_content_text(
        as_marked_section(
            Bold("Команды для работы с очередью:"),
            as_key_value(Text("ℹ️ ", Code("показать очередь")),
                         "показывает информацию о наличии свободный мест и очереди"),
            as_key_value(
                Text("🙋 ", Code("свободное место"), ' / ', Code("встать в очередь"), ' / ', Code("приеду сегодня")),
                "добавляете себя в конец очереди, если еще не в ней"),
            as_key_value(Text("✋ ", Code("покинуть очередь"), ' / ', Code("не приеду сегодня")),
                         "удаляете себя из очереди, если находитесь в ней"),
            marker="• ", ))
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="ℹ️ Показать очередь", switch_inline_query_current_chat='Показать очередь'))
    builder.add(InlineKeyboardButton(text="🙋 Встать в очередь", switch_inline_query_current_chat='Встать в очередь'))
    builder.add(InlineKeyboardButton(text="✋ Покинуть очередь", switch_inline_query_current_chat='Покинуть очередь'))
    builder.add(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"back_to_main"))
    builder.adjust(1)
    await callback.message.edit_text(**content.as_kwargs(), reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("other_commands"))
async def other_commands(callback: CallbackQuery):
    """Обработчик показа команд для работы с очередью"""
    content = await get_content_text(
        as_marked_section(
            Bold("Дополнительно:"),
            as_key_value(Text("✉️ ", Code("написать разработчику <СООБЩЕНИЕ>")),
                         "отправляет сообщение разработчику бота"),
            as_key_value(Text("🏁 ", Code("Поиграть в тетрис"), " 🏎️"),
                         "поиграть в гонки, как на старом добром тетрисе (/tetris)"),
            marker="• ", ))
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✉️ Написать разработчику",
                                     switch_inline_query_current_chat='Написать разработчику <СООБЩЕНИЕ>'))
    builder.add(InlineKeyboardButton(text="🏁 Поиграть в тетрис 🏎️", switch_inline_query_current_chat='Тетрис'))
    builder.add(InlineKeyboardButton(text="🔒 В разработке", callback_data=f"restrict_commands"))
    builder.add(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"back_to_main"))
    builder.adjust(1)
    await callback.message.edit_text(**content.as_kwargs(), reply_markup=builder.as_markup())


async def get_content_text(commands):
    content = as_list(
        f"Привет, я бот для бронирования парковочных мест!",
        f"Для работы с ботом достаточно написать одну из следующих команд в чат:",
        commands,
        HashTag("#commands"),
        sep="\n\n",
    )
    return content


@router.callback_query(F.data.startswith("restrict_commands"), flags={"check_callback": True})
async def restrict_commands(callback: CallbackQuery):
    pass
