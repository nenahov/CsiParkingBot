from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BufferedInputFile,
    InputMediaPhoto,
    InputRichBlockButtons,
    InputRichBlockParagraph,
    InputRichBlockSectionHeading,
    InputRichBlockTable,
    InputRichMessage,
    RichBlockTableCell,
    RichMessageButton,
    RichTextButton,
)
from aiogram.utils.formatting import Bold, as_key_value, as_list
from aiogram.utils.keyboard import InlineKeyboardBuilder

from handlers.driver_callback import add_button, MyCallback
from models.driver import Driver
from models.user_audit import UserActionType
from services.audit_service import AuditService
from services.notification_sender import send_reply, EventType, NotificationSender, send_alarm
from services.telegram_ui import edit_rich
from utils.cars_generator import generate_carousel_image, cars_count, extra_cars_count

router = Router()


@router.callback_query(MyCallback.filter(F.action == "settings"),
                       flags={"check_driver": True, "check_callback": True})
async def show_settings_menu(event, session, driver: Driver):
    content = Bold("Выберите, что хотите настроить:")
    content += '\n\n'
    content += as_list(as_key_value("📅 Расписание", "Бронирование места по дням недели;"),
                       as_key_value("🛎️ Настройки уведомлений", "Включение/выключение уведомлений;"),
                       as_key_value("🏎️ Выбрать аватар",
                                    "Выбор модельки Вашей машины, которая будет отображаться на карте, когда Вы приехали."))
    builder = InlineKeyboardBuilder()
    add_button("📅 Расписание...", "edit-schedule", driver.chat_id, builder)
    add_button("🛎️ Настройки уведомлений...", "edit-alarms", driver.chat_id, builder)
    add_button("🏎️ Выбрать аватар...", "edit-avatar", driver.chat_id, builder)
    add_button("⬅️ Назад", "show-status", driver.chat_id, builder)
    builder.adjust(1)
    await send_reply(event, content, builder)


@router.callback_query(MyCallback.filter(F.action == "edit-alarms"),
                       flags={"check_driver": True, "check_callback": True})
async def edit_alarms(event, driver: Driver):
    disabled_events = driver.attributes.get("disabled_events", [])
    builder = InlineKeyboardBuilder()
    fallback_lines = ["🛎️ Настройки уведомлений:", ""]
    rows = [[
        _alarm_cell("Уведомление", header=True),
        _alarm_cell("Описание", header=True),
        _alarm_cell("Состояние", header=True),
        _alarm_cell("Тест", header=True),
    ]]

    for event_type in EventType:
        is_on = event_type.name not in disabled_events
        state = "✅ Включено" if is_on else "❌ Выключено"
        fallback_lines.append(
            f"{state} {event_type.value['button_text']} — {event_type.value['description']}"
        )
        add_button(
            f"{'✅' if is_on else '❌'} {event_type.value['button_text']}",
            "set-alarms",
            driver.chat_id,
            builder,
            event_type=event_type.name,
            bool_value=is_on,
        )
        add_button(
            "Тест",
            "test-alarms",
            driver.chat_id,
            builder,
            event_type=event_type.name,
        )
        rows.append([
            _alarm_cell(event_type.value["button_text"]),
            _alarm_cell(event_type.value["description"]),
            _alarm_action_cell(
                state,
                "set-alarms",
                driver.chat_id,
                event_type.name,
                bool_value=is_on,
            ),
            _alarm_action_cell(
                "Отправить",
                "test-alarms",
                driver.chat_id,
                event_type.name,
            ),
        ])

    add_button("⬅️ Назад", "show-status", driver.chat_id, builder)
    builder.adjust(2)
    fallback_lines.extend(["", "Выберите действие в кнопках рядом с уведомлением."])
    rich_message = InputRichMessage(
        blocks=[
            InputRichBlockSectionHeading(text="🛎️ Настройки уведомлений", size=1),
            InputRichBlockParagraph(
                text="Переключайте уведомления и отправляйте тест прямо в таблице."
            ),
            InputRichBlockTable(
                cells=rows,
                is_bordered=True,
                is_striped=True,
                is_compact=True,
            ),
            InputRichBlockParagraph(
                text="Изменения сохраняются сразу."
            ),
            InputRichBlockButtons(
                buttons=[
                    RichMessageButton(
                        text="⬅️ Назад",
                        callback_data=MyCallback(
                            action="show-status",
                            user_id=driver.chat_id,
                            spot_id=None,
                            day_num=None,
                            event_type=None,
                            bool_value=None,
                        ).pack(),
                    )
                ],
                align="center",
            ),
        ]
    )
    await edit_rich(
        event,
        rich_message,
        personal=event.message.chat.type != "private",
        fallback_text="\n".join(fallback_lines),
        fallback_reply_markup=builder.as_markup(),
    )


def _alarm_cell(text, *, header: bool = False):
    return RichBlockTableCell(
        text=text,
        align="left" if not header else "center",
        valign="middle",
        is_header=True if header else None,
    )


def _alarm_action_cell(text, action, user_id, event_type, *, bool_value=None):
    return _alarm_cell(
        RichTextButton(
            button=RichMessageButton(
                text=text,
                callback_data=MyCallback(
                    action=action,
                    user_id=user_id,
                    spot_id=None,
                    day_num=None,
                    event_type=event_type,
                    bool_value=bool_value,
                ).pack(),
                style="link",
            )
        ),
        header=False,
    )


@router.callback_query(MyCallback.filter(F.action == "set-alarms"),
                       flags={"check_driver": True, "check_callback": True})
async def set_alarms(event, callback_data: MyCallback, session, driver: Driver, current_day):
    disabled_events = driver.attributes.get("disabled_events", [])
    if callback_data.bool_value:
        if callback_data.event_type not in disabled_events:
            disabled_events.append(callback_data.event_type)
    elif callback_data.event_type in disabled_events:
        disabled_events.remove(callback_data.event_type)
    driver.attributes["disabled_events"] = disabled_events
    await session.commit()
    await edit_alarms(event, driver)


@router.callback_query(MyCallback.filter(F.action == "test-alarms"),
                       flags={"check_driver": True, "check_callback": True})
async def test_alarms(event: CallbackQuery, callback_data: MyCallback, session, driver: Driver, current_day):
    test_driver = Driver()
    test_driver.title = "ФИО_водителя"
    test_driver.description = "ФИО_водителя"
    test_driver.attributes = {}
    await NotificationSender(event.bot).send_to_driver(EventType[callback_data.event_type], test_driver, driver,
                                                       add_message="",
                                                       spot_id=0, karma_change=0,
                                                       my_date=current_day.strftime('%a %d.%m.%Y'), txt='Выходной\n\n')
    await event.answer()


@router.callback_query(MyCallback.filter(F.action == "edit-avatar"),
                       flags={"check_driver": True, "check_callback": True})
async def edit_avatar(event: CallbackQuery, driver: Driver):
    current_index = driver.attributes.get("car_index", driver.id)
    cars_count_for_driver = extra_cars_count if driver.attributes.get("extra_cars", 0) > 0 else cars_count
    photo = generate_carousel_image(current_index, cars_count_for_driver)
    await event.message.answer_photo(caption="🏎️ Выберите свой аватар:", show_caption_above_media=True,
                                     photo=BufferedInputFile(photo.getvalue(), filename="carousel.png"),
                                     reply_markup=get_carousel_keyboard(current_index, driver.chat_id, 'success'))
    await event.answer()


@router.callback_query(MyCallback.filter(F.action == "set-avatar"),
                       flags={"check_driver": True, "check_callback": True})
async def set_avatar(event: CallbackQuery, callback_data: MyCallback, session, driver: Driver, current_day):
    driver.attributes["car_index"] = callback_data.spot_id
    await send_alarm(event, "🏎️ Аватар успешно установлен")
    await AuditService(session).log_action(driver.id, UserActionType.CHOOSE_AVATAR, current_day,
                                           num=callback_data.spot_id,
                                           description=f"{driver.description} выбрал аватар {callback_data.spot_id}")


@router.callback_query(F.data.startswith("carousel:"), flags={"check_driver": True})
async def carousel_callback(event: CallbackQuery, driver: Driver):
    """
    Обрабатывает нажатия на кнопки "⬅️" и "➡️".
    Из callback data определяется направление и вычисляется новый индекс,
    после чего обновляется изображение и клавиатура.
    """
    try:
        _, index_str, direction = event.data.split(":")
        current_index = int(index_str)
    except ValueError:
        await event.answer("Ошибка данных!", show_alert=True)
        return
    cars_count_for_driver = extra_cars_count if driver.attributes.get("extra_cars", 0) > 0 else cars_count
    new_index = (current_index + int(direction)) % cars_count_for_driver
    current_index = driver.attributes.get("car_index", driver.id)
    style = 'primary' if new_index != current_index else 'success'
    photo = generate_carousel_image(new_index, cars_count_for_driver)
    try:
        await event.message.edit_media(
            media=InputMediaPhoto(caption="🏎️ Выберите свой аватар:", show_caption_above_media=True,
                                  media=BufferedInputFile(photo.getvalue(), filename="carousel.png")),
            reply_markup=get_carousel_keyboard(new_index, driver.chat_id, style))
    except Exception as e:
        # Если редактирование сообщения не удалось, отправляем новое фото
        await event.message.answer_photo(caption="🏎️ Выберите свой аватар:", show_caption_above_media=True,
                                         photo=BufferedInputFile(photo.getvalue(), filename="carousel.png"),
                                         reply_markup=get_carousel_keyboard(new_index, driver.chat_id, style))

    await event.answer()


def get_carousel_keyboard(current_index: int, chat_id: int, style: str) -> InlineKeyboardMarkup:
    """
    Создает инлайн-клавиатуру для навигации карусели с кнопками "⬅️" и "➡️".
    Callback data хранит текущий индекс и направление смены.
    """
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="⬅️", callback_data=f"carousel:{current_index}:-1"))
    builder.add(InlineKeyboardButton(text="➡️", callback_data=f"carousel:{current_index}:1"))
    builder.add(InlineKeyboardButton(text="⬅️⬅️⬅️", callback_data=f"carousel:{current_index}:-3"))
    builder.add(InlineKeyboardButton(text="➡️➡️➡️", callback_data=f"carousel:{current_index}:3"))
    add_button("☑️ Выбрать этот аватар", "set-avatar", chat_id, builder, spot_id=current_index, style=style)
    builder.adjust(2, 2, 1)
    return builder.as_markup()
