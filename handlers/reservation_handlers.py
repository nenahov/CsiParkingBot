from datetime import date, timedelta

from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InputRichBlockButtons,
    InputRichBlockParagraph,
    InputRichBlockSectionHeading,
    InputRichBlockTable,
    InputRichMessage,
    RichBlockTableCell,
    RichMessageButton,
    RichTextButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from handlers.driver_callback import add_button, MyCallback
from models.driver import Driver
from services.reservation_service import ReservationService
from services.telegram_ui import edit_rich

router = Router()


@router.callback_query(MyCallback.filter(F.action == "choose-day"),
                       flags={"check_driver": True, "check_callback": True})
async def handle_day_selection(callback: CallbackQuery, callback_data: MyCallback, session, driver: Driver,
                               current_day):
    spot_id = callback_data.spot_id
    day_of_week = callback_data.day_num

    reservation_service = ReservationService(session)
    reservations = await reservation_service.get_spot_reservations(spot_id, day_of_week)
    can_reserve = _can_reserve(reservations, driver.id, current_day, day_of_week)

    builder = InlineKeyboardBuilder()
    mine = any(res.driver_id == driver.id for res in reservations)
    if mine:
        add_button(
            "❌ Освободить место", "cancel_spot", driver.chat_id, builder,
            spot_id, day_of_week, event_type="day-detail",
        )
        builder.add(InlineKeyboardButton(text="🏝️ Буду отсутствовать N дней",
                                         switch_inline_query_current_chat='Меня не будет <ЧИСЛО> дня/дней'))
    elif can_reserve:
        add_button(
            "✅ Забронировать", "reserve_spot", driver.chat_id, builder,
            spot_id, day_of_week, event_type="day-detail",
        )

    add_button("⬅️ Назад", "select-spot", driver.chat_id, builder, spot_id)
    builder.adjust(1)

    day_name = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][day_of_week]
    fallback_lines = [f"🅿️ Место {spot_id}, {day_name}"]
    rows = [[
        _cell("Статус", header=True),
        _cell("Водитель", header=True),
        _cell("Приедет", header=True),
    ]]
    # День/действие — отдельная строка: действие не должно визуально
    # приписываться одному из нескольких водителей с бронью.
    if not reservations:
        rows.append([
            _action_cell(
                "⚪ Свободно · Забронировать",
                "reserve_spot",
                driver.chat_id,
                spot_id,
                day_of_week,
                event_type="day-detail",
            ),
            _cell("—"),
            _cell("—"),
        ])
        fallback_lines.append("Свободно!")
    else:
        if mine:
            day_status = _action_cell(
                "🟡 Моя бронь · Освободить",
                "cancel_spot",
                driver.chat_id,
                spot_id,
                day_of_week,
                event_type="day-detail",
            )
        elif can_reserve:
            day_status = _action_cell(
                "🟢 Забронировать",
                "reserve_spot",
                driver.chat_id,
                spot_id,
                day_of_week,
                event_type="day-detail",
            )
        else:
            day_status = _cell("🔴 Занято", align="center")
        rows.append([day_status, _cell("Состояние места"), _cell(day_name)])

        for reservation in reservations:
            absent_until = (
                reservation.driver.absent_until.strftime("%a %d.%m.%Y")
                if reservation.driver.is_absent(current_day)
                else "по расписанию"
            )
            rows.append([
                _cell("🔴 Забронировано", align="center"),
                _cell(reservation.driver.description),
                _cell(absent_until),
            ])
            fallback_lines.append(
                f"Забронировано: {reservation.driver.description} — {absent_until}"
            )

    if len(reservations) >= 2:
        fallback_lines.append(
            "В день приезда первого из списка все остальные резервы будут удалены."
        )
    if any(res.driver_id == driver.id for res in reservations):
        fallback_lines.append(
            "Для отпуска можно воспользоваться командой «Буду отсутствовать N дней»."
        )

    rich_buttons = []
    if mine:
        rich_buttons.append(
            RichMessageButton(
                text="🏝️ Буду отсутствовать N дней",
                switch_inline_query_current_chat="Меня не будет <ЧИСЛО> дня/дней",
            )
        )
    rich_buttons.append(
        RichMessageButton(
            text="⬅️ Назад",
            callback_data=MyCallback(
                action="select-spot",
                user_id=driver.chat_id,
                spot_id=spot_id,
                day_num=None,
                event_type=None,
                bool_value=None,
            ).pack(),
        )
    )
    rich_message = InputRichMessage(blocks=[
        InputRichBlockSectionHeading(
            text=f"🅿️ Место {spot_id} · {day_name}",
            size=1,
        ),
        InputRichBlockTable(
            cells=rows,
            is_bordered=True,
            is_striped=True,
            is_compact=True,
        ),
        InputRichBlockParagraph(
            text=(
                f"Количество бронирований: {len(reservations)}. "
                "Действие доступно прямо в колонке «Статус»."
            )
        ),
        InputRichBlockButtons(buttons=rich_buttons, align="center"),
    ])
    await edit_rich(
        callback,
        rich_message,
        personal=callback.message.chat.type != "private",
        fallback_text="\n".join(fallback_lines),
        fallback_reply_markup=builder.as_markup(),
    )


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

    await _render_originating_schedule(callback, callback_data, spot_id, session, driver, current_day)


@router.callback_query(MyCallback.filter(F.action == "cancel_spot"),
                       flags={"check_driver": True, "check_callback": True})
async def handle_cancel_reservation(callback: CallbackQuery, callback_data: MyCallback, session, driver, current_day):
    day_of_week = callback_data.day_num

    reservation_service = ReservationService(session)
    await reservation_service.delete_reservation(driver.id, day_of_week)
    await callback.answer("🗑️ Бронь отменена")
    await _render_originating_schedule(
        callback, callback_data, callback_data.spot_id, session, driver, current_day
    )


async def _render_originating_schedule(callback, callback_data, spot_id, session, driver, current_day):
    """После действия вернуться к тому же экрану расписания, откуда нажали."""
    if callback_data.event_type == "day-detail":
        await handle_day_selection(
            callback,
            MyCallback(
                action="choose-day",
                user_id=driver.chat_id,
                spot_id=spot_id,
                day_num=callback_data.day_num,
                event_type=None,
                bool_value=None,
            ),
            session,
            driver,
            current_day,
        )
        return
    await render_spot_schedule(callback, spot_id, session, driver, current_day)


@router.callback_query(MyCallback.filter(F.action == "select-spot"),
                       flags={"check_driver": True, "check_callback": True})
async def start_reservation_process(callback: CallbackQuery, callback_data: MyCallback, session, driver, current_day):
    """Обработчик выбора парковочного места"""
    spot_id = callback_data.spot_id
    await render_spot_schedule(callback, spot_id, session, driver, current_day)


async def render_spot_schedule(callback: CallbackQuery, spot_id, session, driver, current_day):
    """Показать недельное расписание с действиями прямо в ячейках статуса."""

    current_week_day = current_day.weekday()  # 0-6 (пн-вс)

    fallback_lines = [f"🅿️ Место {spot_id}"]
    rows = [[
        _cell("День", header=True),
        _cell("Статус", header=True),
        _cell("Водители", header=True),
    ]]

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
        can_reserve = _can_reserve(reservations, driver.id, current_day, day_num)
        # 🔴- other and not me, 🟠 - other and me, 🟡 - only me, 🟢 - free
        status = "🔴" if other and not me else ("🟡" if other and me else ("🟢" if me else "⚪️"))
        add_button(f"{status} {day_name}" + (' ✔️' if day_num == current_week_day else ''),
                   "choose-day", driver.chat_id, builder, spot_id, day_num,
                   event_type="day-detail")
        fallback_lines.append(
            f"{day_name}: {', '.join(res.driver.title for res in reservations) if reservations else 'место свободно 🫶'}"
        )
        if me:
            status_cell = _action_cell(
                "🟡 Моя бронь · Освободить",
                "cancel_spot",
                driver.chat_id,
                spot_id,
                day_num,
                event_type="weekly-schedule",
            )
        elif can_reserve:
            status_cell = _action_cell(
                "🟢 Забронировать",
                "reserve_spot",
                driver.chat_id,
                spot_id,
                day_num,
                event_type="weekly-schedule",
            )
        else:
            status_cell = _cell("🔴 Занято", align="center")

        rows.append([
            _cell(f"{day_name}" + (" ✔️" if day_num == current_week_day else "")),
            status_cell,
            _cell(", ".join(res.driver.title for res in reservations) if reservations else "—"),
        ])
    fallback_lines.append(
        "✔️ — текущий день недели. Доступные действия находятся в колонке «Статус»."
    )
    add_button("⬅️ Назад", "choose-spots", driver.chat_id, builder)
    builder.adjust(3, 3, 1)
    rich = InputRichMessage(
        blocks=[
            InputRichBlockSectionHeading(text=f"🅿️ Место {spot_id}", size=1),
            InputRichBlockTable(
                cells=rows,
                is_bordered=True,
                is_striped=True,
                is_compact=True,
            ),
            InputRichBlockParagraph(
                text="Если действие доступно, нажмите его прямо в колонке «Статус»."
            ),
            InputRichBlockButtons(
                buttons=[
                    RichMessageButton(
                        text="⬅️ Назад",
                        callback_data=MyCallback(
                            action="choose-spots",
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
        callback,
        rich,
        personal=callback.message.chat.type != "private",
        fallback_text="\n".join(fallback_lines),
        fallback_reply_markup=builder.as_markup(),
    )


def _cell(text, *, header: bool = False, align: str = "left"):
    return RichBlockTableCell(
        text=text,
        align="center" if header else align,
        valign="middle",
        is_header=True if header else None,
    )


def _action_cell(text, action, user_id, spot_id, day_num, event_type=None):
    return _cell(
        RichTextButton(
            button=RichMessageButton(
                text=text,
                callback_data=MyCallback(
                    action=action,
                    user_id=user_id,
                    spot_id=spot_id,
                    day_num=day_num,
                    event_type=event_type,
                    bool_value=None,
                ).pack(),
                style="link",
            )
        ),
        align="center",
    )


def _date_for_weekday(current_day: date, day_num: int) -> date:
    """Ближайшее календарное occurrence дня недели, включая сегодняшний день."""
    return current_day + timedelta(days=(day_num - current_day.weekday()) % 7)


def _can_reserve(reservations, driver_id: int, current_day: date, day_num: int) -> bool:
    """Можно занять место, если ни одна чужая бронь не активна в этот день."""
    target_day = _date_for_weekday(current_day, day_num)
    return all(
        reservation.driver_id == driver_id
        or reservation.driver.is_absent(target_day)
        for reservation in reservations
    )
