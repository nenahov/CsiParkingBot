from datetime import timedelta

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.formatting import Text, as_marked_section, Bold, as_key_value, Italic, Code
from aiogram.utils.keyboard import InlineKeyboardBuilder

from handlers.driver_callback import add_button, MyCallback
from models.driver import Driver
from services.reservation_service import ReservationService

router = Router()


@router.callback_query(MyCallback.filter(F.action == "choose-day"),
                       flags={"check_driver": True, "check_callback": True})
async def handle_day_selection(callback: CallbackQuery, callback_data: MyCallback, session, driver: Driver,
                               current_day):
    spot_id = callback_data.spot_id
    day_of_week = callback_data.day_num

    reservation_service = ReservationService(session)
    reservations = await reservation_service.get_spot_reservations(spot_id, day_of_week)

    builder = InlineKeyboardBuilder()
    if any(res.driver_id == driver.id for res in reservations):
        add_button("❌ Освободить место", "cancel_spot", driver.chat_id, builder, spot_id, day_of_week)
        builder.add(InlineKeyboardButton(text="🏝️ Буду отсутствовать N дней",
                                         switch_inline_query_current_chat='Меня не будет <ЧИСЛО> дня/дней'))
    elif all(res.driver.is_absent(current_day + timedelta(days=1)) for res in reservations):
        add_button("✅ Забронировать", "reserve_spot", driver.chat_id, builder, spot_id, day_of_week)

    add_button("⬅️ Назад", "select-spot", driver.chat_id, builder, spot_id)
    builder.adjust(1)

    drivers_info = Bold("Свободно!") if not reservations else as_marked_section(
        Bold("Забронировано:"),
        *[as_key_value(f"{res.driver.description}",
                       f"приедет в {res.driver.absent_until.strftime('%a %d.%m.%Y') if res.driver.is_absent(current_day) else ''}")
          for res in reservations],
        marker="• ", )

    content = Text("🅿️ Место ", Bold(f"{spot_id}"), ", ",
                   Bold(f"{['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'][day_of_week]}"), ":\n\n",
                   drivers_info,
                   "\n\n",
                   as_key_value(Bold(f"Количество резерваций"), f"{len(reservations)}"),
                   '' if len(reservations) < 2 else Italic(
                       "\n\nВ день приезда первого из списка все остальные резервы будут удалены"),
                   Text("\n\nЕсли вы уезжаете в отпуск или в командировку, можете не снимать свой резерв, ",
                        "а воспользоваться командой\n", Code("🏝️ Буду отсутствовать N дней"),
                        "\nпосле вашего приезда все резервы будут восстановлены автоматически.\n"
                        "А во время отсутствия ваше место могут забронировать ваши напарники "
                        "или воспользоваться коллеги, встав в очередь!") if any(
                       res.driver_id == driver.id for res in reservations) else ""
                   )
    await callback.message.edit_text(**content.as_kwargs(), reply_markup=builder.as_markup())


@router.callback_query(MyCallback.filter(F.action == "reserve_spot"),
                       flags={"check_driver": True, "check_callback": True})
async def handle_reservation(callback: CallbackQuery, callback_data: MyCallback, session, driver, current_day):
    spot_id = callback_data.spot_id
    day_of_week = callback_data.day_num
    reservation_service = ReservationService(session)
    try:
        await reservation_service.create_reservation({
            "day_of_week": day_of_week,
            "parking_spot_id": spot_id,
            "driver_id": driver.id
        })
        await callback.answer("✅ Место забронировано!")
    except ValueError as e:
        await callback.answer(f"❌ Ошибка: {str(e)}")

    await handle_day_selection(callback, callback_data, session, driver, current_day)


@router.callback_query(MyCallback.filter(F.action == "cancel_spot"),
                       flags={"check_driver": True, "check_callback": True})
async def handle_cancel_reservation(callback: CallbackQuery, callback_data: MyCallback, session, driver, current_day):
    day_of_week = callback_data.day_num

    reservation_service = ReservationService(session)
    await reservation_service.delete_reservation(driver.id, day_of_week)
    await callback.answer("🗑️ Бронь отменена")
    await handle_day_selection(callback, callback_data, session, driver, current_day)


@router.callback_query(MyCallback.filter(F.action == "select-spot"),
                       flags={"check_driver": True, "check_callback": True})
async def start_reservation_process(callback: CallbackQuery, callback_data: MyCallback, session, driver, current_day):
    """Обработчик выбора парковочного места"""
    spot_id = callback_data.spot_id
    current_week_day = current_day.weekday()  # 0-6 (пн-вс)

    content = Text(f"🅿️ Выбрано место {spot_id}.\n\n")

    week_days = [
        ("Пн", 0), ("Вт", 1), ("Ср", 2), ("Чт", 3),
        ("Пт", 4), ("Сб", 5), ("Вс", 6)
    ]
    reservation_service = ReservationService(session)
    builder = InlineKeyboardBuilder()
    for day_name, day_num in week_days:
        reservations = await reservation_service.get_spot_reservations(spot_id, day_num)
        me = any(res.driver_id == driver.id for res in reservations)
        other = any(res.driver_id != driver.id for res in reservations)
        # 🔴- other and not me, 🟠 - other and me, 🟡 - only me, 🟢 - free
        status = "🔴" if other and not me else ("🟡" if other and me else ("🟢" if me else "⚪️"))
        add_button(f"{status} {day_name}" + (' ✔️' if day_num == current_week_day else ''),
                   "choose-day", driver.chat_id, builder, spot_id, day_num)
        content += Code(
            f"{status} {day_name}:\t..\t{', '.join(res.driver.title for res in reservations) if reservations else 'место свободно 🫶'}\n")
    content += (f"\n✔️ - текущий день недели.\n\n"
                f"Выберите день недели:")
    add_button("⬅️ Назад", "choose-spots", driver.chat_id, builder)
    builder.adjust(3, 3, 1)

    await callback.message.edit_text(**content.as_kwargs(), reply_markup=builder.as_markup())
