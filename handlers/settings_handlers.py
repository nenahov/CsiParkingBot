from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.utils.formatting import Text, Bold, as_key_value
from aiogram.utils.keyboard import InlineKeyboardBuilder

from handlers.driver_callback import add_button, MyCallback
from models.driver import Driver
from services.notification_sender import send_reply, EventType, NotificationSender

router = Router()


@router.callback_query(MyCallback.filter(F.action == "edit-alarms"),
                       flags={"check_driver": True, "check_callback": True})
async def edit_alarms(event, session, driver: Driver):
    builder = InlineKeyboardBuilder()
    content = Text(Bold("🛎️ Настройки уведомлений:"))
    # content += '\n\n'
    # content += Bold("✅ - уведомление приходит,\n❌ - уведомление не приходит")
    content += '\n\n'
    disabled_events = driver.attributes.get("disabled_events", [])
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
    await edit_alarms(event, session, driver)


@router.callback_query(MyCallback.filter(F.action == "test-alarms"),
                       flags={"check_driver": True, "check_callback": True})
async def test_alarms(event: CallbackQuery, callback_data: MyCallback, session, driver: Driver, current_day):
    await NotificationSender(event.bot).send_to_driver(EventType[callback_data.event_type], driver, driver, "",
                                                       0, 0, current_day.strftime('%a %d.%m.%Y'))
    await event.answer()
