import json
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendRichMessage
from aiogram.types import InputRichBlockButtons, InputRichBlockTable

from handlers.driver_callback import MyCallback
from handlers.game_race_handlers import (
    _deadline_text, _panel_keyboard, _panel_message, _public_race_message,
    _send_selection_window, _race_chat_id, execute_race, get_game_message,
    get_race_keyboard, get_state,
    restore_race_deadlines, router, start_race_callback,
)
from utils.game_race_utils import GameState, SELECTION_WINDOW


def players(count=8):
    result = []
    for number in range(1, count + 1):
        result.append(SimpleNamespace(
            id=number, chat_id=number + 100,
            title=f"Водитель {number}", username=f"driver{number}",
            attributes={"karma": 100},
            get_karma=lambda: 100,
        ))
    return result


def state(count=8):
    race = GameState({"1": [2, 3, 5], "2": [3, 4, 3]})
    race.player_ids = list(range(1, count + 1))
    race.begin_selection(datetime(2026, 10, 15, 12, 0), seed=987)
    return race


def complete_choice(race, participant, *, plan="steady"):
    race.set_wheels(participant, participant.id % 3)
    race.choose_plan(participant.id, plan)
    count = len(race.player_ids)
    for slot in range(race.target_count()):
        source = race.player_ids[(participant.id + slot) % count]
        recipient = race.player_ids[(participant.id + race.target_count() + slot) % count]
        race.set_transfer(participant.id, slot, "source", source)
        race.set_transfer(participant.id, slot, "recipient", recipient)


class RaceChoiceTests(unittest.TestCase):
    def test_window_closes_registration_immediately(self):
        race = state()
        self.assertEqual(SELECTION_WINDOW, timedelta(days=2))
        self.assertEqual(
            datetime.fromisoformat(race.selection_deadline),
            datetime(2026, 10, 17, 12, 0),
        )
        with self.assertRaises(ValueError):
            race.add_player(players()[0])
        self.assertFalse(race.deadline_reached(datetime(2026, 10, 15, 13, 0)))
        self.assertFalse(race.deadline_reached(datetime(2026, 10, 16, 12, 0)))
        self.assertFalse(race.deadline_reached(datetime(2026, 10, 17, 11, 59, 59)))
        self.assertTrue(race.deadline_reached(datetime(2026, 10, 17, 12, 0)))
        self.assertTrue(race.deadline_reached(datetime(2026, 10, 17, 12, 0, 1)))

    def test_deadline_text_includes_date_and_time(self):
        race = state()
        self.assertEqual(_deadline_text(race), "17.10 12:00")
        public = _public_race_message(race, players())
        self.assertIn("17.10 12:00", str(public.model_dump(exclude_none=True)))

    def test_scaled_transfers_guard_and_plan_changes(self):
        for count, target_count in ((8, 3), (9, 4), (10, 4), (11, 5), (12, 5)):
            race = state(count)
            self.assertEqual(race.target_count(), target_count)
            complete_choice(race, players(count)[0])
            self.assertEqual(len(race.actions[1].transfers), target_count)
            for target_id in range(2, target_count + 2):
                race.toggle_guard(1, target_id)
            with self.assertRaises(ValueError):
                race.toggle_guard(1, target_count + 2)
            with self.assertRaises(ValueError):
                race.toggle_guard(1, 1)
            race.confirm(1)
            self.assertIn(1, race.confirmed)
            race.choose_plan(1, "late")
            self.assertEqual(len(race.actions[1].transfers), target_count)
            self.assertEqual(race.actions[1].plan, "late")
            self.assertNotIn(1, race.confirmed)

    def test_roundtrip_and_lane_mapping(self):
        race = state(8)
        complete_choice(race, players()[0], plan="early")
        race.toggle_guard(1, 2)
        race.confirm(1)
        restored = GameState.from_dict(race.to_dict())
        self.assertEqual(restored.to_dict(), race.to_dict())
        self.assertEqual(restored.resolve_actions()[0].transfers,
                         ((1, 4), (2, 5), (3, 6)))
        self.assertEqual(restored.resolve_actions()[0].guards, (1,))
        self.assertEqual(restored.resolve_actions()[0].plan, "early")

    def test_early_start_only_after_everyone_confirms(self):
        race = state()
        for participant in players():
            complete_choice(race, participant)
            race.confirm(participant.id)
        self.assertTrue(race.all_ready())
        race.choose_plan(2, "early")
        self.assertFalse(race.all_ready())
        race.fill_missing_choices()
        self.assertEqual(race.actions[2].kind, "nitro")

    def test_private_panel_shows_one_step_and_public_table_stays_compact(self):
        race = state()
        race.set_wheels(players()[0], 0)
        panel = _panel_message(race, players()[0], players())
        tables = [block for block in panel.blocks if isinstance(block, InputRichBlockTable)]
        self.assertEqual(tables, [])
        self.assertIn("Маршрут 1 из 3", panel.blocks[0].text)
        actions = {
            MyCallback.unpack(button.callback_data).action
            for block in panel.blocks if isinstance(block, InputRichBlockButtons)
            for button in block.buttons
        }
        self.assertEqual(actions, {"race_target", "race_step"})
        public = _public_race_message(race, players())
        public_table = next(
            block for block in public.blocks if isinstance(block, InputRichBlockTable)
        )
        self.assertEqual(len(public_table.cells[0]), 2)
        self.assertTrue(public_table.is_compact)
        self.assertTrue(any(
            isinstance(block, InputRichBlockButtons) for block in public.blocks
        ))

    def test_fallback_private_buttons_keep_original_group(self):
        race = state()
        participant = players()[0]
        markup = _panel_keyboard(race, participant, players(), chat_id=-100123456)
        callbacks = [
            button.callback_data
            for row in markup.inline_keyboard for button in row
        ]
        self.assertTrue(all(len(value.encode()) <= 64 for value in callbacks))
        self.assertIn("-100123456", callbacks[0])
        self.assertEqual(
            _race_chat_id(SimpleNamespace(
                message=SimpleNamespace(chat=SimpleNamespace(id=participant.chat_id))
            ), MyCallback.unpack(callbacks[0])),
            -100123456,
        )

    def test_early_start_has_admin_middleware_flag(self):
        handler = next(
            item for item in router.callback_query.handlers
            if item.callback.__name__ == "race_start_now_callback"
        )
        self.assertTrue(handler.flags["check_admin"])


class RaceSettlementTests(unittest.IsolatedAsyncioTestCase):
    async def test_race_pays_exact_pool_and_cleans_up(self):
        race = state()
        entrants = players()
        for participant in entrants:
            complete_choice(race, participant)
            race.confirm(participant.id)
        session = AsyncMock()
        bot = AsyncMock()
        with (
            patch("handlers.game_race_handlers.get_state", new_callable=AsyncMock,
                  return_value=race),
            patch("handlers.game_race_handlers.save_state", new_callable=AsyncMock),
            patch("handlers.game_race_handlers.remove_state", new_callable=AsyncMock)
            as remove,
            patch("handlers.game_race_handlers.DriverService") as driver_service,
            patch("handlers.game_race_handlers.AuditService") as audit_service,
            patch("handlers.game_race_handlers.create_race_gif") as render,
        ):
            driver_service.return_value.get_by_id = AsyncMock(
                side_effect=lambda participant_id: entrants[participant_id - 1]
            )
            audit_service.return_value.log_action = AsyncMock()
            self.assertTrue(await execute_race(bot, -123, session))
            render.assert_called_once()
            remove.assert_awaited_once_with(-123, session)
            session.commit.assert_awaited()
            bot.send_animation.assert_awaited_once()
            self.assertEqual(bot.send_rich_message.await_count, 2)
            sent = [call[0] for call in bot.mock_calls
                    if call[0] in ("send_rich_message", "send_animation")]
            self.assertEqual(sent, [
                "send_rich_message", "send_animation", "send_rich_message",
            ])
        self.assertEqual(sum(p.attributes["karma"] - 100 for p in entrants), 8 * 50)


class RaceStateRestoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_state_does_not_prevent_deadline_restoration(self):
        active = state().to_dict()
        saved = json.dumps({
            "-101": {"player_ids": [1], "wheels": {}, "weather": {}},
            "-102": None,
            "-103": {"phase": "selection"},  # incomplete new-format record
            "-104": active,
        })
        service = Mock()
        service.get_parameter = AsyncMock(return_value=saved)
        scheduler = Mock()
        with (
            patch("handlers.game_race_handlers.ParamService", return_value=service),
            patch("handlers.game_race_handlers._race_scheduler", scheduler),
        ):
            await restore_race_deadlines(Mock(), Mock())
        scheduler.add_job.assert_called_once()
        self.assertEqual(scheduler.add_job.call_args.kwargs["id"], "race-deadline--104")
        self.assertEqual(
            scheduler.add_job.call_args.kwargs["run_date"],
            datetime(2026, 10, 17, 12, 0),
        )

    async def test_legacy_state_is_not_treated_as_active_game(self):
        service = Mock()
        service.get_parameter = AsyncMock(return_value=json.dumps({
            "-101": {"player_ids": [1], "wheels": {}, "weather": {}},
        }))
        with patch("handlers.game_race_handlers.ParamService", return_value=service):
            self.assertIsNone(await get_state(-101, Mock()))


class RaceLobbyKeyboardTests(unittest.IsolatedAsyncioTestCase):
    async def test_lobby_rules_announce_two_day_selection_window(self):
        race = GameState({"1": [2, 3, 5], "2": [3, 4, 3]})
        content, _, _ = await get_game_message(race, Mock())
        self.assertIn("На выбор даётся 2 суток.", content.as_html())

    async def test_lobby_only_offers_registration_and_admin_start(self):
        race = GameState({"1": [2, 3, 5], "2": [3, 4, 3]})
        for count, expected in ((0, {"join_race"}), (8, {"join_race", "start_race"})):
            race.player_ids = list(range(1, count + 1))
            keyboard = (await get_race_keyboard(race)).as_markup()
            actions = {
                MyCallback.unpack(button.callback_data).action
                for row in keyboard.inline_keyboard for button in row
            }
            self.assertEqual(actions, expected)


class RaceSelectionWindowTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_schedules_two_day_deadline_and_announces_window(self):
        race = GameState({"1": [2, 3, 5], "2": [3, 4, 3]})
        race.player_ids = list(range(1, 9))
        bot = Mock()
        message = SimpleNamespace(chat=SimpleNamespace(id=-100123), bot=bot)
        callback = SimpleNamespace(message=message, answer=AsyncMock())
        audit = Mock()
        audit.log_action = AsyncMock()
        scheduler = Mock()
        with (
            patch("handlers.game_race_handlers.get_state",
                  new_callable=AsyncMock, return_value=race),
            patch("handlers.game_race_handlers._send_selection_window",
                  new_callable=AsyncMock, return_value=Mock()),
            patch("handlers.game_race_handlers.AuditService", return_value=audit),
            patch("handlers.game_race_handlers._race_scheduler", scheduler),
            patch("handlers.game_race_handlers.datetime") as clock,
        ):
            clock.now.return_value = datetime(2026, 11, 8, 12)
            clock.fromisoformat.side_effect = datetime.fromisoformat
            await start_race_callback(
                callback, Mock(), Mock(),
                SimpleNamespace(id=1, title="Админ"), None,
            )
        self.assertEqual(race.selection_deadline, "2026-11-10T12:00:00")
        scheduler.add_job.assert_called_once()
        self.assertEqual(
            scheduler.add_job.call_args.kwargs["run_date"],
            datetime(2026, 11, 10, 12),
        )
        callback.answer.assert_awaited_once_with("Окно выбора открыто на 2 суток")

    async def test_publishes_and_saves_before_deleting_lobby(self):
        bot = Mock()
        sent = SimpleNamespace(message_id=456)
        bot.send_rich_message = AsyncMock(return_value=sent)
        bot.send_message = AsyncMock()
        message = SimpleNamespace(
            chat=SimpleNamespace(id=-100123), bot=bot, delete=AsyncMock(),
        )
        callback = SimpleNamespace(message=message)
        race = state()
        service = Mock()
        service.get_by_id = AsyncMock(
            side_effect=lambda player_id: players()[player_id - 1],
        )

        async def save_before_delete(*_):
            message.delete.assert_not_awaited()

        with (
            patch("handlers.game_race_handlers.DriverService", return_value=service),
            patch("handlers.game_race_handlers.save_state",
                  new_callable=AsyncMock, side_effect=save_before_delete) as save,
        ):
            result = await _send_selection_window(callback, race, Mock())
        self.assertIs(result, sent)
        self.assertEqual(race.public_message_id, 456)
        save.assert_awaited_once()
        message.delete.assert_awaited_once()
        bot.send_message.assert_not_awaited()

    async def test_rich_failure_sends_tagged_plain_message_before_deleting(self):
        bot = Mock()
        bot.send_rich_message = AsyncMock(side_effect=TelegramBadRequest(
            method=SendRichMessage(
                chat_id=-100123,
                rich_message=_public_race_message(state(), players()),
            ),
            message="Rich messages are not supported",
        ))
        bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=789))
        message = SimpleNamespace(
            chat=SimpleNamespace(id=-100123), bot=bot, delete=AsyncMock(),
        )
        service = Mock()
        service.get_by_id = AsyncMock(
            side_effect=lambda player_id: players()[player_id - 1],
        )
        with (
            patch("handlers.game_race_handlers.DriverService", return_value=service),
            patch("handlers.game_race_handlers.save_state", new_callable=AsyncMock),
        ):
            result = await _send_selection_window(
                SimpleNamespace(message=message), state(), Mock(),
            )
        self.assertEqual(result.message_id, 789)
        self.assertEqual(
            len(bot.send_message.await_args.kwargs["entities"]), 8,
        )
        message.delete.assert_awaited_once()

    async def test_failed_publication_keeps_lobby_and_no_deadline(self):
        race = GameState({"1": [2, 3, 5], "2": [3, 4, 3]})
        race.player_ids = list(range(1, 9))
        message = SimpleNamespace(chat=SimpleNamespace(id=-100123), bot=Mock())
        callback = SimpleNamespace(message=message, answer=AsyncMock())
        with (
            patch("handlers.game_race_handlers.get_state",
                  new_callable=AsyncMock, return_value=race),
            patch("handlers.game_race_handlers._send_selection_window",
                  new_callable=AsyncMock, return_value=None),
            patch("handlers.game_race_handlers.send_alarm",
                  new_callable=AsyncMock) as alarm,
            patch("handlers.game_race_handlers.save_state",
                  new_callable=AsyncMock) as save,
            patch("handlers.game_race_handlers._schedule_deadline") as schedule,
        ):
            await start_race_callback(
                callback, Mock(), Mock(),
                SimpleNamespace(id=1, title="Админ"), None,
            )
        alarm.assert_awaited_once()
        save.assert_not_awaited()
        schedule.assert_not_called()


if __name__ == "__main__":
    unittest.main()
