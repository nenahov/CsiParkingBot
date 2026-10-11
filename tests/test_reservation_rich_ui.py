import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.types import InputRichBlockTable, RichTextButton

from handlers.driver_callback import MyCallback
from handlers.reservation_handlers import (
    _action_cell,
    _can_reserve,
    _date_for_weekday,
    handle_day_selection,
    render_spot_schedule,
)


class ReservationRichUiTests(unittest.TestCase):
    def test_action_in_status_cell_keeps_driver_spot_day_and_operation(self):
        cell = _action_cell(
            "🟢 Забронировать",
            "reserve_spot",
            user_id=42,
            spot_id=17,
            day_num=3,
        )

        self.assertIsInstance(cell.text, RichTextButton)
        callback = MyCallback.unpack(cell.text.button.callback_data)
        self.assertEqual(callback.action, "reserve_spot")
        self.assertEqual(callback.user_id, 42)
        self.assertEqual(callback.spot_id, 17)
        self.assertEqual(callback.day_num, 3)

    def test_status_cell_can_represent_cancellation_as_direct_action(self):
        cell = _action_cell(
            "🟡 Моя бронь · Освободить",
            "cancel_spot",
            user_id=42,
            spot_id=17,
            day_num=0,
        )

        callback = MyCallback.unpack(cell.text.button.callback_data)
        self.assertEqual(callback.action, "cancel_spot")
        self.assertEqual(callback.day_num, 0)


class ReservationScheduleTests(unittest.IsolatedAsyncioTestCase):
    def test_weekday_resolves_to_nearest_calendar_occurrence(self):
        monday = date(2026, 10, 12)
        self.assertEqual(_date_for_weekday(monday, 0), monday)
        self.assertEqual(_date_for_weekday(monday, 2), date(2026, 10, 14))
        self.assertEqual(_date_for_weekday(monday, 6), date(2026, 10, 18))

    def test_absence_is_checked_against_selected_occurrence_and_owner_can_cancel(self):
        absent_driver = SimpleNamespace(
            is_absent=lambda target: target < date(2026, 10, 15)
        )
        active_driver = SimpleNamespace(is_absent=lambda _: False)
        own_reservation = SimpleNamespace(driver_id=42, driver=absent_driver)
        other_reservation = SimpleNamespace(driver_id=84, driver=active_driver)

        self.assertTrue(_can_reserve([own_reservation], 42, date(2026, 10, 12), 2))
        self.assertFalse(_can_reserve([other_reservation], 42, date(2026, 10, 12), 2))
        self.assertTrue(
            _can_reserve(
                [
                    SimpleNamespace(driver_id=84, driver=absent_driver)
                ],
                42,
                date(2026, 10, 12),
                2,
            )
        )
        cutoff_today = SimpleNamespace(
            is_absent=lambda target: target < date(2026, 10, 15)
        )
        self.assertFalse(
            _can_reserve(
                [SimpleNamespace(driver_id=84, driver=cutoff_today)],
                42,
                date(2026, 10, 12),
                3,
            )
        )

    async def test_rich_schedule_uses_status_cells_not_weekday_inline_buttons(self):
        callback = SimpleNamespace(
            message=SimpleNamespace(
                chat=SimpleNamespace(type="private"),
            )
        )
        driver = SimpleNamespace(id=42, chat_id=42)
        session = object()

        with patch(
                "handlers.reservation_handlers.ReservationService"
        ) as reservation_service, patch(
            "handlers.reservation_handlers.edit_rich",
            new_callable=AsyncMock,
        ) as send:
            reservation_service.return_value.get_spot_reservations = AsyncMock(
                return_value=[]
            )
            await render_spot_schedule(
                callback,
                spot_id=17,
                session=session,
                driver=driver,
                current_day=date(2026, 10, 12),
            )

        rich_message = send.await_args.args[1]
        schedule_table = next(
            block for block in rich_message.blocks
            if isinstance(block, InputRichBlockTable)
        )
        self.assertEqual(len(schedule_table.cells), 8)
        self.assertTrue(
            all(isinstance(row[1].text, RichTextButton) for row in schedule_table.cells[1:])
        )
        self.assertNotIn("reply_markup", send.await_args.kwargs)
        fallback_keyboard = send.await_args.kwargs["fallback_reply_markup"]
        self.assertEqual(
            sum(len(row) for row in fallback_keyboard.inline_keyboard),
            8,
        )
        rich_action = schedule_table.cells[1][1].text.button
        self.assertEqual(
            MyCallback.unpack(rich_action.callback_data).event_type,
            "weekly-schedule",
        )
        choose_day = MyCallback.unpack(
            fallback_keyboard.inline_keyboard[0][0].callback_data
        )
        self.assertEqual(choose_day.action, "choose-day")
        self.assertEqual(choose_day.event_type, "day-detail")

    async def test_duplicate_reservations_have_a_separate_day_status_row(self):
        callback = SimpleNamespace(
            message=SimpleNamespace(chat=SimpleNamespace(type="private"))
        )
        driver = SimpleNamespace(id=42, chat_id=42)
        other_one = SimpleNamespace(
            driver_id=84,
            driver=SimpleNamespace(
                description="Водитель 1",
                absent_until=date(2026, 10, 20),
                is_absent=lambda _: True,
            ),
        )
        other_two = SimpleNamespace(
            driver_id=85,
            driver=SimpleNamespace(
                description="Водитель 2",
                absent_until=date(2026, 10, 20),
                is_absent=lambda _: True,
            ),
        )
        with patch(
                "handlers.reservation_handlers.ReservationService"
        ) as reservation_service, patch(
            "handlers.reservation_handlers.edit_rich",
            new_callable=AsyncMock,
        ) as send:
            reservation_service.return_value.get_spot_reservations = AsyncMock(
                return_value=[other_one, other_two]
            )
            await handle_day_selection(
                callback,
                MyCallback(
                    action="choose-day",
                    user_id=42,
                    spot_id=17,
                    day_num=2,
                    event_type=None,
                    bool_value=None,
                ),
                session=object(),
                driver=driver,
                current_day=date(2026, 10, 12),
            )

        rich_message = send.await_args.args[1]
        table = next(
            block for block in rich_message.blocks
            if isinstance(block, InputRichBlockTable)
        )
        self.assertEqual(len(table.cells), 4)
        # The day-level status is separate; both driver rows remain plain
        # reservation information, so the action is not attributed to a driver.
        self.assertIsInstance(table.cells[1][0].text, RichTextButton)
        self.assertEqual(
            MyCallback.unpack(table.cells[1][0].text.button.callback_data).event_type,
            "day-detail",
        )
        fallback_keyboard = send.await_args.kwargs["fallback_reply_markup"]
        fallback_action = MyCallback.unpack(
            fallback_keyboard.inline_keyboard[0][0].callback_data
        )
        self.assertEqual(fallback_action.action, "reserve_spot")
        self.assertEqual(fallback_action.event_type, "day-detail")
        self.assertNotIsInstance(table.cells[2][0].text, RichTextButton)
        self.assertNotIsInstance(table.cells[3][0].text, RichTextButton)


class ReservationCallbackRedrawTests(unittest.IsolatedAsyncioTestCase):
    async def test_action_from_day_detail_redraws_day_detail(self):
        callback = object()
        callback_data = MyCallback(
            action="reserve_spot",
            user_id=42,
            spot_id=17,
            day_num=4,
            event_type="day-detail",
            bool_value=None,
        )
        driver = SimpleNamespace(chat_id=42)
        with patch(
                "handlers.reservation_handlers.handle_day_selection",
                new_callable=AsyncMock,
        ) as render_day, patch(
            "handlers.reservation_handlers.render_spot_schedule",
            new_callable=AsyncMock,
        ) as render_week:
            from handlers.reservation_handlers import _render_originating_schedule

            await _render_originating_schedule(
                callback, callback_data, 17, object(), driver, date(2026, 10, 12)
            )

        render_day.assert_awaited_once()
        render_week.assert_not_awaited()
        self.assertEqual(render_day.await_args.args[1].day_num, 4)

    async def test_action_from_week_view_redraws_week_view(self):
        callback = object()
        callback_data = MyCallback(
            action="reserve_spot",
            user_id=42,
            spot_id=17,
            day_num=None,
            event_type=None,
            bool_value=None,
        )
        driver = SimpleNamespace(chat_id=42)
        with patch(
                "handlers.reservation_handlers.handle_day_selection",
                new_callable=AsyncMock,
        ) as render_day, patch(
            "handlers.reservation_handlers.render_spot_schedule",
            new_callable=AsyncMock,
        ) as render_week:
            from handlers.reservation_handlers import _render_originating_schedule

            await _render_originating_schedule(
                callback, callback_data, 17, object(), driver, date(2026, 10, 12)
            )

        render_week.assert_awaited_once()
        render_day.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
