from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, BufferedInputFile, InputMediaPhoto
from aiogram.utils.formatting import Text, Bold, as_key_value, as_list
from aiogram.utils.keyboard import InlineKeyboardBuilder

from handlers.driver_callback import add_button, MyCallback
from models.driver import Driver
from models.user_audit import UserActionType
from services.audit_service import AuditService
from services.notification_sender import send_reply, EventType, NotificationSender, send_alarm
from utils.cars_generator import generate_carousel_image, cars_count

router = Router()


@router.callback_query(MyCallback.filter(F.action == "settings"),
                       flags={"check_driver": True, "check_callback": True})
async def show_settings_menu(event, session, driver: Driver):
    content = Text(Bold("Выберите, что хотите настроить:"))
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
    content = Text(Bold("🛎️ Настройки уведомлений:"))
    # content += '\n\n'
    # content += Bold("✅ - уведомление приходит,\n❌ - уведомление не приходит")
    content += '\n\n'
    disabled_events = driver.attributes.get("disabled_events", [])
    builder = InlineKeyboardBuilder()
    for event_type in EventType:
        is_on = event_type.name not in disabled_events
        content += ('✅ ' if is_on else '❌ ')
        content += as_key_value(event_type.value["button_text"], event_type.value["description"])
        content += '\n'
        add_button(('✅ ' if is_on else '❌ ') + event_type.value["button_text"], "set-alarms", driver.chat_id, builder,
                   event_type=event_type.name, bool_value=is_on)
        add_button('Тест', "test-alarms", driver.chat_id, builder,
                   event_type=event_type.name)

    add_button("⬅️ Назад", "show-status", driver.chat_id, builder)
    builder.adjust(2)
    await send_reply(event, content, builder)


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
    photo = generate_carousel_image(current_index)
    await event.message.answer_photo(caption="🏎️ Выберите свой аватар:", show_caption_above_media=True,
                                     photo=BufferedInputFile(photo.getvalue(), filename="carousel.png"),
                                     reply_markup=get_carousel_keyboard(current_index, driver.chat_id))
    await event.answer()


@router.callback_query(MyCallback.filter(F.action == "set-avatar"),
                       flags={"check_driver": True, "check_callback": True})
async def set_avatar(event: CallbackQuery, callback_data: MyCallback, session, driver: Driver, current_day):
    driver.attributes["car_index"] = callback_data.spot_id
    await send_alarm(event, "🏎️ Аватар успешно установлен")
    await AuditService(session).log_action(driver.id, UserActionType.CHOOSE_AVATAR, current_day,
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

    new_index = (current_index + int(direction)) % cars_count

    photo = generate_carousel_image(new_index)
    try:
        await event.message.edit_media(
            media=InputMediaPhoto(caption="🏎️ Выберите свой аватар:", show_caption_above_media=True,
                                  media=BufferedInputFile(photo.getvalue(), filename="carousel.png")),
            reply_markup=get_carousel_keyboard(new_index, driver.chat_id))
    except Exception as e:
        # Если редактирование сообщения не удалось, отправляем новое фото
        await event.message.answer_photo(caption="🏎️ Выберите свой аватар:", show_caption_above_media=True,
                                         photo=BufferedInputFile(photo.getvalue(), filename="carousel.png"),
                                         reply_markup=get_carousel_keyboard(new_index, driver.chat_id))

    await event.answer()


def get_carousel_keyboard(current_index: int, chat_id: int) -> InlineKeyboardMarkup:
    """
    Создает инлайн-клавиатуру для навигации карусели с кнопками "⬅️" и "➡️".
    Callback data хранит текущий индекс и направление смены.
    """
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="⬅️", callback_data=f"carousel:{current_index}:-1"))
    builder.add(InlineKeyboardButton(text="➡️", callback_data=f"carousel:{current_index}:1"))
    builder.add(InlineKeyboardButton(text="⬅️⬅️⬅️", callback_data=f"carousel:{current_index}:-3"))
    builder.add(InlineKeyboardButton(text="➡️➡️➡️", callback_data=f"carousel:{current_index}:3"))
    add_button("☑️ Выбрать этот аватар", "set-avatar", chat_id, builder, spot_id=current_index)
    builder.adjust(2, 2, 1)
    return builder.as_markup()
