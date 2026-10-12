from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BufferedInputFile,
    InputMediaPhoto,
    InputRichBlockButtons,
    InputRichBlockParagraph,
    InputRichBlockPhoto,
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
from services.telegram_ui import answer_rich, edit_rich
from utils.cars_generator import (
    cars_count,
    extra_cars_count,
    generate_avatar_gallery_image,
    generate_avatar_preview_image,
    generate_carousel_image,
)

router = Router()
AVATAR_PAGE_SIZE = 12


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
    await _send_avatar_gallery(event, driver, page=_avatar_page_for_current(driver))
    await event.answer()


@router.callback_query(MyCallback.filter(F.action == "set-avatar"),
                       flags={"check_driver": True, "check_callback": True})
async def set_avatar(event: CallbackQuery, callback_data: MyCallback, session, driver: Driver, current_day):
    cars_count_for_driver = _cars_count_for_driver(driver)
    avatar_index = callback_data.spot_id
    if avatar_index is None or not 0 <= avatar_index < cars_count_for_driver:
        await event.answer("Эта машинка недоступна.", show_alert=True)
        return
    driver.attributes["car_index"] = avatar_index
    await send_alarm(event, "🏎️ Аватар успешно установлен")
    await AuditService(session).log_action(driver.id, UserActionType.CHOOSE_AVATAR, current_day,
                                           num=avatar_index,
                                           description=f"{driver.description} выбрал аватар {avatar_index}")


def _cars_count_for_driver(driver: Driver) -> int:
    return extra_cars_count if driver.attributes.get("extra_cars", 0) > 0 else cars_count


def get_avatar_page_count(cars_count_for_driver: int) -> int:
    return max(1, (cars_count_for_driver + AVATAR_PAGE_SIZE - 1) // AVATAR_PAGE_SIZE)


def _avatar_page_for_current(driver: Driver) -> int:
    total = _cars_count_for_driver(driver)
    current_index = int(driver.attributes.get("car_index", driver.id)) % total
    return current_index // AVATAR_PAGE_SIZE


def _avatar_rich_button(
        text: str,
        action: str,
        chat_id: int,
        *,
        spot_id: int | None = None,
        page: int | None = None,
        style: str | None = None,
) -> RichMessageButton:
    return RichMessageButton(
        text=text,
        callback_data=MyCallback(
            action=action,
            user_id=chat_id,
            spot_id=spot_id,
            day_num=page,
            event_type=None,
            bool_value=None,
        ).pack(),
        style=style,
    )


def get_avatar_gallery_keyboard(
        page: int,
        cars_count_for_driver: int,
        chat_id: int,
        current_index: int,
) -> InlineKeyboardMarkup:
    """Legacy inline-клавиатура для галереи, если rich-сообщения недоступны."""
    builder = InlineKeyboardBuilder()
    page_count = get_avatar_page_count(cars_count_for_driver)
    first_index = page * AVATAR_PAGE_SIZE
    for offset in range(AVATAR_PAGE_SIZE):
        avatar_index = first_index + offset
        if avatar_index >= cars_count_for_driver:
            break
        label = f"✅ {avatar_index + 1}" if avatar_index == current_index else str(avatar_index + 1)
        add_button(label, "avatar-preview", chat_id, builder,
                   spot_id=avatar_index, day_num=page)
    builder.adjust(3)
    add_button("◀️", "avatar-page", chat_id, builder,
               spot_id=max(0, page - 1), day_num=page,
               style="primary" if page > 0 else "secondary")
    add_button(f"{page + 1}/{page_count}", "avatar-page", chat_id, builder,
               spot_id=page, day_num=page)
    add_button("▶️", "avatar-page", chat_id, builder,
               spot_id=min(page_count - 1, page + 1), day_num=page,
               style="primary" if page < page_count - 1 else "secondary")
    builder.adjust(3)
    return builder.as_markup()


def get_avatar_preview_keyboard(
        page: int,
        cars_count_for_driver: int,
        chat_id: int,
        avatar_index: int,
) -> InlineKeyboardMarkup:
    """Legacy inline-клавиатура для крупного превью."""
    builder = InlineKeyboardBuilder()
    add_button("✅ Выбрать этот аватар", "set-avatar", chat_id,
               builder, spot_id=avatar_index, style="success")
    add_button("↩️ К списку", "avatar-page", chat_id, builder, spot_id=page, day_num=page)
    builder.adjust(1)
    return builder.as_markup()


def build_avatar_gallery_rich_message(
        page: int,
        cars_count_for_driver: int,
        chat_id: int,
        current_index: int,
) -> InputRichMessage:
    page_count = get_avatar_page_count(cars_count_for_driver)
    first_index = page * AVATAR_PAGE_SIZE
    cells = []
    for offset in range(AVATAR_PAGE_SIZE):
        avatar_index = first_index + offset
        if avatar_index >= cars_count_for_driver:
            break
        label = f"✅ {avatar_index + 1}" if avatar_index == current_index else str(avatar_index + 1)
        cells.append(
            RichBlockTableCell(
                text=RichTextButton(
                    button=_avatar_rich_button(
                        label,
                        "avatar-preview",
                        chat_id,
                        spot_id=avatar_index,
                        page=page,
                        style="success" if avatar_index == current_index else "link",
                    )
                ),
                align="center",
                valign="middle",
            )
        )

    while len(cells) % 3:
        cells.append(RichBlockTableCell(text=""))

    table_rows = [cells[index:index + 3] for index in range(0, len(cells), 3)]
    navigation = []
    if page > 0:
        navigation.append(_avatar_rich_button(
            "◀️",
            "avatar-page",
            chat_id,
            spot_id=page - 1,
            page=page,
            style="link",
        ))
    if page < page_count - 1:
        navigation.append(_avatar_rich_button(
            "▶️",
            "avatar-page",
            chat_id,
            spot_id=page + 1,
            page=page,
            style="link",
        ))
    return InputRichMessage(
        blocks=[
            InputRichBlockSectionHeading(text="🏎️ Выберите аватар", size=1),
            InputRichBlockPhoto(
                photo=InputMediaPhoto(
                    media=BufferedInputFile(
                        generate_avatar_gallery_image(
                            first_index,
                            cars_count_for_driver,
                            selected_index=current_index,
                        ).getvalue(),
                        filename="avatar-gallery.png",
                    )
                )
            ),
            InputRichBlockParagraph(
                text=f"Страница {page + 1}/{page_count} · Варианты {first_index + 1}–"
                     f"{min(first_index + AVATAR_PAGE_SIZE, cars_count_for_driver)}. "
                     "Нажмите номер под нужной машинкой для крупного превью."
            ),
            InputRichBlockTable(
                cells=table_rows,
                is_bordered=True,
                is_striped=False,
                is_compact=True,
            ),
            InputRichBlockButtons(buttons=navigation, align="center"),
        ]
    )


def build_avatar_preview_rich_message(
        page: int,
        cars_count_for_driver: int,
        chat_id: int,
        avatar_index: int,
) -> InputRichMessage:
    navigation = [
        _avatar_rich_button(
            "✅ Выбрать этот аватар",
            "set-avatar",
            chat_id,
            spot_id=avatar_index,
            page=page,
            style="success",
        ),
        _avatar_rich_button("↩️ К списку", "avatar-page", chat_id,
                            spot_id=page, page=page, style="link"),
    ]
    return InputRichMessage(
        blocks=[
            InputRichBlockSectionHeading(
                text=f"🏎️ Машинка #{avatar_index + 1}",
                size=1,
            ),
            InputRichBlockPhoto(
                photo=InputMediaPhoto(
                    media=BufferedInputFile(
                        generate_avatar_preview_image(avatar_index).getvalue(),
                        filename="avatar-preview.png",
                    )
                )
            ),
            InputRichBlockParagraph(
                text="Если вам нравится этот вариант, подтвердите выбор кнопкой ниже."
            ),
            InputRichBlockButtons(buttons=navigation, align="center"),
        ]
    )


async def _send_avatar_gallery(event: CallbackQuery, driver: Driver, page: int):
    total = _cars_count_for_driver(driver)
    page = max(0, min(page, get_avatar_page_count(total) - 1))
    current_index = int(driver.attributes.get("car_index", driver.id)) % total
    rich_message = build_avatar_gallery_rich_message(
        page, total, driver.chat_id, current_index
    )
    fallback_photo = generate_avatar_gallery_image(
        page * AVATAR_PAGE_SIZE, total, selected_index=current_index
    )
    fallback_markup = get_avatar_gallery_keyboard(
        page, total, driver.chat_id, current_index
    )
    try:
        await answer_rich(
            event,
            rich_message,
            personal=event.message.chat.type != "private",
        )
    except TelegramBadRequest:
        await event.message.answer_photo(
            caption=f"🏎️ Выберите аватар — страница {page + 1}/"
                    f"{get_avatar_page_count(total)}",
            show_caption_above_media=True,
            photo=BufferedInputFile(fallback_photo.getvalue(), filename="avatar-gallery.png"),
            reply_markup=fallback_markup,
        )


async def _edit_avatar_screen(event: CallbackQuery, rich_message: InputRichMessage,
                              fallback_photo, fallback_markup):
    try:
        await edit_rich(
            event,
            rich_message,
            personal=event.message.chat.type != "private",
        )
    except TelegramBadRequest:
        try:
            await event.message.edit_media(
                media=InputMediaPhoto(
                    caption="🏎️ Выберите аватар:",
                    show_caption_above_media=True,
                    media=BufferedInputFile(
                        fallback_photo.getvalue(), filename="avatar-picker.png"
                    ),
                ),
                reply_markup=fallback_markup,
            )
        except Exception:
            await event.message.answer_photo(
                caption="🏎️ Выберите аватар:",
                show_caption_above_media=True,
                photo=BufferedInputFile(
                    fallback_photo.getvalue(), filename="avatar-picker.png"
                ),
                reply_markup=fallback_markup,
            )


@router.callback_query(MyCallback.filter(F.action == "avatar-page"),
                       flags={"check_driver": True, "check_callback": True})
async def avatar_page(event: CallbackQuery, callback_data: MyCallback, driver: Driver):
    total = _cars_count_for_driver(driver)
    page = callback_data.spot_id or 0
    page = max(0, min(page, get_avatar_page_count(total) - 1))
    current_index = int(driver.attributes.get("car_index", driver.id)) % total
    await _edit_avatar_screen(
        event,
        build_avatar_gallery_rich_message(page, total, driver.chat_id, current_index),
        generate_avatar_gallery_image(
            page * AVATAR_PAGE_SIZE, total, selected_index=current_index
        ),
        get_avatar_gallery_keyboard(page, total, driver.chat_id, current_index),
    )
    await event.answer()


@router.callback_query(MyCallback.filter(F.action == "avatar-preview"),
                       flags={"check_driver": True, "check_callback": True})
async def avatar_preview(event: CallbackQuery, callback_data: MyCallback, driver: Driver):
    total = _cars_count_for_driver(driver)
    avatar_index = callback_data.spot_id
    if avatar_index is None or not 0 <= avatar_index < total:
        await event.answer("Эта машинка недоступна.", show_alert=True)
        return
    page = avatar_index // AVATAR_PAGE_SIZE
    await _edit_avatar_screen(
        event,
        build_avatar_preview_rich_message(page, total, driver.chat_id, avatar_index),
        generate_avatar_preview_image(avatar_index),
        get_avatar_preview_keyboard(page, total, driver.chat_id, avatar_index),
    )
    await event.answer()


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
