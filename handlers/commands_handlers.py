from aiogram import Router, F
from aiogram.filters import Command
from aiogram.filters import or_f
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.formatting import as_list, as_marked_section, Bold, as_key_value, HashTag, Code, Text, TextLink, \
    Italic, Pre
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import constants
from handlers.driver_callback import MyCallback

router = Router()


@router.callback_query(or_f(MyCallback.filter(F.action == "pass"), F.data == "pass"),
                       flags={"check_driver": True})
async def pass_callback(callback: CallbackQuery):
    await callback.answer()


@router.message(or_f(Command("help", "?", "commands"),
                     F.text.regexp(r"(?i)(.*доступные команды)|(.*помощь.* бот)|(.*список.* команд)")))
async def help_command(message: Message):
    await main_commands(message, True)


@router.callback_query(F.data.startswith("back_to_main"))
async def back_to_main(callback: CallbackQuery):
    await main_commands(callback.message, False)


async def main_commands(message, is_new: bool):
    content = as_list(
        Bold(f"Привет, я бот для бронирования парковочных мест!"),
        f"Для работы с ботом достаточно написать ему в чат или послать команду из меню.",
        Bold("Как это работает:"),
        as_marked_section(
            Bold("В течение рабочего дня:"),
            "Вы можете ставить или забирать свою машину на парковке.",
            marker="• ",
        ),
        as_marked_section(
            Bold(f"В {constants.new_day_begin_hour}:00:"),
            "Все парковочные места освобождаются.",
            "Очередь на свободные места очищается.",
            "Начинается прием заявок на свободные места на следующий день.",
            marker="• ",
        ),
        as_marked_section(
            Bold("Если у вас есть бронь:"),
            "Вы можете подтвердить (🚗 Приеду...), что приедете, или сообщить, что не сможете приехать (🫶 Не приеду...)",
            "Если вы отменяете бронь, место становится доступным для других пользователей! 🫶",
            Text("При подтверждении брони, на карте (") + Code("показать карту") + ") будет нарисована ваша машинка 🚙",
            "Если вы ничего не нажали - тоже не страшно: забронированное место останется за Вами.",
            marker="• ",
        ),
        as_marked_section(
            Bold("Если у вас нет брони:"),
            "Вы можете встать «в очередь» на розыгрыш свободных мест (/status → 🚗 Приеду... → 🙋 Встать в очередь).",
            marker="• ",
        ),
        as_marked_section(
            Bold(f"Начиная с {constants.new_day_queue_hour}:00:"),
            "Свободные места разыгрываются между теми, кто стоит в очереди.",
            "Вероятность получения места зависит от вашей Кармы 🫶.",
            "Вы получите уведомление с предложением занять выпавшее место.",
            "Нужно будет откликнуться на это предложение до 9:00 утра. В противном случае место будет разыграно заново!",
            "После 9:00 свободные места разыгрываются с периодичностью 10 минут.",
            marker="• ",
        ),
        as_marked_section(
            Bold("Тихие часы 😴:"),
            "С 01:00 до 07:00 розыгрыши свободных мест не проводятся.",
            marker="• ",
        ),
        "Если возникнут вопросы или нужна помощь – обращайтесь!",
        sep="\n\n",
    )
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="⁉️ С чего начать?", callback_data=f"starter_info"))
    builder.add(InlineKeyboardButton(text="ℹ️ Информация", callback_data=f"info_commands"))
    builder.add(InlineKeyboardButton(text="🏪 Магазин", callback_data=f"shop_commands"))
    # builder.add(InlineKeyboardButton(text="🫶 Бронирование места", callback_data=f"reservation_commands"))
    # builder.add(InlineKeyboardButton(text="🙋 Очередь на парковку", callback_data=f"queue_commands"))
    builder.add(InlineKeyboardButton(text="🤖 Другое", callback_data=f"other_commands"))
    builder.adjust(1)
    if is_new:
        await message.answer(**content.as_kwargs(), reply_markup=builder.as_markup())
    else:
        await message.edit_text(**content.as_kwargs(), reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("starter_info"))
async def starter_info(callback: CallbackQuery):
    """Обработчик показа 'С чего начать?'"""
    content = Text(
        Bold(f"Раздел 'С чего начать⁉️'\n"),
        f"\nНе забудьте прочитать описание на главной странице 'Помощи'\n")
    content += Bold("\nПосле прочтения справки о боте:")

    me = await callback.bot.get_me()
    bot_username = me.username

    if callback.message.chat.type != 'private':
        content += Bold("\n\n0. Перейдите в личные сообщения с ботом: ")
        content += TextLink(f"Перейти @{bot_username}", url=f"https://t.me/{bot_username}")

    content += as_marked_section(
        Bold("\n\n1. Забронируйте свое место парковки на дни недели\n") +
        Italic("Чтобы место было забронировано за Вами в эти дни"),
        "Запустите команду /status",
        Text("Нажмите на кнопку '⚙️ Настройки...' → '📅 Расписание...' (",
             TextLink(f"появляется только в ЛС", url=f"https://t.me/{bot_username}"), ")"),
        "Выберите место и дни недели, которые хотите забронировать",
        marker="• ", )

    content += as_marked_section(
        Bold("\n\n2. Зарабатывайте 'Карму'\n") +
        Italic("Карма влияет на шанс выбора, когда несколько человек в очереди и освободилось место"),
        "Запустите команду /status",
        "Нажмите на кнопку '🎲 Карма! 🆓'",
        "Заходите раз в день на новый розыгрыш.",
        marker="• ", )

    content += as_marked_section(
        Bold("\n\n3. Не бойтесь задавать вопросы\n") +
        Italic("Бот дорабатывается и нам важно Ваше мнение"),
        "Нажмите на кнопку '✉️ Написать разработчику' и отправьте сообщение",
        "Или напишите в общем чате или лично 🤝",
        marker="• ", )

    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="ℹ️ Мой статус", switch_inline_query_current_chat='Мой статус'))
    builder.add(InlineKeyboardButton(text="Написать разработчику",
                                     style='primary', icon_custom_emoji_id='5253742260054409879',
                                     switch_inline_query_current_chat='Написать разработчику: "Вместо этого текста напишите Ваше сообщение"'))
    builder.add(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"back_to_main"))
    builder.adjust(1)
    await callback.message.edit_text(**content.as_kwargs(), reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("info_commands"))
async def info_commands(callback: CallbackQuery):
    """Обработчик показа информационных команд"""
    content = await get_content_text(
        as_marked_section(
            Bold("Команды для просмотра информации:"),
            as_key_value(Text("ℹ️ ", Code("мой статус")), "показывает информацию о вас и доступные действия"),
            as_key_value(Text("🗺️ ", Code("показать карту парковки")),
                         "показывает карту парковки на текущий момент"),
            as_key_value(Text("🗺️ ", Code("показать карту на завтра")), "показывает карту парковки на завтра"),
            as_key_value(Text("⛅️ ", Code("прогноз погоды")), "показывает прогноз погоды на сегодняшний день"),
            as_key_value(Text("☀️ ", Code("прогноз погоды на завтра")), "показывает прогноз погоды на завтра"),
            as_key_value(Text("📝 ", Code("показать список команд")), "показывает список команд"),
            marker="• ", ))
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="ℹ️ Мой статус", switch_inline_query_current_chat='Мой статус'))
    builder.add(InlineKeyboardButton(text="🗺️ Показать карту", switch_inline_query_current_chat='Показать карту'))
    builder.add(InlineKeyboardButton(text="🗺️ Карта на завтра",
                                     switch_inline_query_current_chat='Показать карту на завтра'))
    builder.add(InlineKeyboardButton(text="⛅️ Прогноз погоды", switch_inline_query_current_chat='Прогноз погоды'))
    builder.add(InlineKeyboardButton(text="☀️ Прогноз погоды на завтра",
                                     switch_inline_query_current_chat='Прогноз погоды на завтра'))
    builder.add(
        InlineKeyboardButton(text="📝 Показать список команд", switch_inline_query_current_chat='Список команд'))
    builder.add(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"back_to_main"))
    builder.adjust(1, 2, 2, 1, 1)
    await callback.message.edit_text(**content.as_kwargs(), reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("shop_commands"))
async def shop_commands(callback: CallbackQuery):
    """Обработчик показа информации о функциях магазина"""
    content = Bold(f"🏪 Магазин добрых дел 🫶")

    me = await callback.bot.get_me()
    bot_username = me.username

    if callback.message.chat.type != 'private':
        content += Bold("\n\n0. Перейдите в личные сообщения с ботом: ")
        content += TextLink(f"Перейти @{bot_username}", url=f"https://t.me/{bot_username}")

    content += Bold("\n\n1. Сделайте новый магазин со слотами для продажи\n")
    content += "Напишите боту в ЛС следующий текст:\n"
    content += Pre("""Новый магазин добрых дел
10 - Описание первого слота (5)
75 - Описание второго слота 
12 - Описание третьего слота (45)
""")
    content += "Бот покажет, что магазин создан, а также дальнейшую инструкцию\n"
    content += Italic("\nВ данном примере будет три слота с ценами: 10, 75, 12 (+НДС) в количестве 5, ∞, 45 шт.")

    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="🏪 Создать магазин", switch_inline_query_current_chat='Новый магазин добрых дел'))
    builder.add(InlineKeyboardButton(text="🫶 Открыть магазин", switch_inline_query_current_chat='Открыть магазин'))
    builder.add(InlineKeyboardButton(text="✖️ Закрыть магазин", switch_inline_query_current_chat='Закрыть магазин'))
    builder.add(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"back_to_main"))
    builder.adjust(1)
    await callback.message.edit_text(**content.as_kwargs(), reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("reservation_commands"))
async def reservation_commands(callback: CallbackQuery):
    """Обработчик показа команд бронирования места"""
    content = await get_content_text(
        as_marked_section(
            Bold("Команды для бронирования места:"),
            as_key_value(Text("🫶 ", Code("буду отсутствовать N дней")),
                         "освобождает свое парковочное место на N дней"),
            as_key_value(Text("🫶 ", Code("не приеду сегодня")), "то же самое, что и 'буду отсутствовать 1 день'"),
            as_key_value(Text("🏎️ ", Code("вернулся раньше")), "возобновляет ваше бронирование парковочного места"),
            as_key_value(Text("🚗 ", Code("приеду сегодня")),
                         "занимаете ранее забронированное место или встаете в очередь"),
            marker="• ", ))
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="🚗 Приеду сегодня", switch_inline_query_current_chat='Приеду сегодня'))
    builder.add(
        InlineKeyboardButton(text="🫶 Не приеду сегодня", switch_inline_query_current_chat='Не приеду сегодня'))
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
                Text("🙋 ", Code("хочу свободное место"), ' / ', Code("встать в очередь"), ' / ',
                     Code("приеду сегодня")),
                "добавляете себя в конец очереди, если еще не в ней"),
            as_key_value(Text("✋ ", Code("покинуть очередь"), ' / ', Code("не приеду сегодня")),
                         "удаляете себя из очереди, если находитесь в ней"),
            marker="• ", ))
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="ℹ️ Показать очередь", switch_inline_query_current_chat='Показать очередь'))
    builder.add(
        InlineKeyboardButton(text="🙋 Встать в очередь", switch_inline_query_current_chat='Встать в очередь'))
    builder.add(
        InlineKeyboardButton(text="✋ Покинуть очередь", switch_inline_query_current_chat='Покинуть очередь'))
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
            as_key_value(Text("❌ ", Code("/XO"), " ⭕"),
                         "поиграть в крестики-нолики (5 в ряд). В ЛС - игра с ботом, в общем чате - с другим игроком!"),
            as_key_value(Text("🫶 ", Code("Доберись до парковки"), " 🅿️"),
                         "поиграть в игру, где нужно найти путь до парковки и можно выиграть 💟"),
            as_key_value(Text("🏁 ", Code("Поиграть в тетрис"), " 🏎️"),
                         "поиграть в гонки, как на старом добром тетрисе (/tetris)"),
            marker="• ", ))
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✉️ Написать разработчику",
                                     switch_inline_query_current_chat='Написать разработчику: "сюда впишите Ваше сообщение"'))
    builder.add(InlineKeyboardButton(text="❌ Поиграть в крестики-нолики ⭕", switch_inline_query_current_chat='/XO'))
    if callback.message.chat.type == 'private':
        builder.add(InlineKeyboardButton(text="🫶 Доберись до парковки 🅿️ (-1 💟)", callback_data=f"game_parking"))
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
