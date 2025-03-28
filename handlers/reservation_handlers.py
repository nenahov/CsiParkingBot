from datetime import datetime

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.reservation_service import ReservationService

router = Router()


@router.callback_query(F.data.startswith("choose-day_"), flags={"check_driver": True})
async def handle_day_selection(callback: CallbackQuery, session, driver):
    _, spot_id, day = callback.data.split("_")
    spot_id = int(spot_id)
    day = int(day)

    reservation_service = ReservationService(session)
    reservations = await reservation_service.get_spot_reservations(spot_id, day)

    builder = InlineKeyboardBuilder()
    if any(res.driver_id == driver.id for res in reservations):
        builder.add(InlineKeyboardButton(
            text="❌ Освободить место",
            callback_data=f"cancel_{spot_id}_{day}"
        ))
    else:
        builder.add(InlineKeyboardButton(
            text="✅ Забронировать",
            callback_data=f"reserve_{spot_id}_{day}"
        ))

    builder.add(InlineKeyboardButton(
        text="⬅️ Назад",
        callback_data=f"select-spot_{spot_id}"
    ))

    await callback.message.edit_text(
        f"Место {spot_id}, {['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'][day]}:\n"
        f"Статус: {len(reservations)} резерваций",
        reply_markup=builder.as_markup()
    )


@router.callback_query(F.data.startswith("reserve_"), flags={"check_driver": True})
async def handle_reservation(callback: CallbackQuery, session, driver):
    _, spot_id, day = callback.data.split("_")
    spot_id = int(spot_id)
    day = int(day)
    reservation_service = ReservationService(session)
    try:
        await reservation_service.create_reservation({
            "day_of_week": day,
            "parking_spot_id": spot_id,
            "driver_id": driver.id
        })
        await callback.answer("✅ Место забронировано!")
    except ValueError as e:
        await callback.answer(f"❌ Ошибка: {str(e)}")

    await handle_day_selection(callback, session, driver)


@router.callback_query(F.data.startswith("cancel_"), flags={"check_driver": True})
async def handle_cancelation(callback: CallbackQuery, session, driver):
    _, spot_id, day = callback.data.split("_")
    spot_id = int(spot_id)
    day = int(day)

    reservation_service = ReservationService(session)
    await reservation_service.delete_reservation(driver.id, spot_id, day)
    await callback.answer("🗑️ Бронь отменена")
    await handle_day_selection(callback, session, driver)


@router.callback_query(F.data.startswith("select-spot_"), flags={"check_driver": True})
async def start_reservation_process(callback: CallbackQuery, session, driver):
    """Обработчик выбора парковочного места"""
    spot_id = int(callback.data.split("_")[-1])
    current_day = datetime.today().weekday()  # 0-6 (пн-вс)

    await callback.message.edit_text(
        text=f"Выбрано место {spot_id}.\n\n🔴 - зарезервировано кем-то,\n🟡 - зарезервировано кем-то и Вами,\n🟢 - зарезервировано только Вами,\n⚪ - свободно.\n\n✔️ - текущий день недели.\n\nВыберите день:",
        reply_markup=await get_weekdays_keyboard(session, driver, spot_id, current_day),
        parse_mode="Markdown"
    )


async def get_weekdays_keyboard(session, driver, spot_id: int, current_day: int) -> InlineKeyboardMarkup:
    """Генератор клавиатуры с днями недели"""
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

        builder.add(InlineKeyboardButton(
            text=f"{status} {day_name}" if day_num != current_day else f"{status} {day_name} ✔️",
            callback_data=f"choose-day_{spot_id}_{day_num}"
        ))
    builder.adjust(4)
    builder.add(InlineKeyboardButton(
        text="⬅️ Назад",
        callback_data=f"choose-spots"
    ))
    return builder.as_markup()
