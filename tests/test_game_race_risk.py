import json
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from aiogram.types import InputRichBlockButtons, InputRichBlockTable, RichTextButton

from handlers.driver_callback import MyCallback
from handlers.game_race_handlers import (
    _panel_keyboard, _panel_message, _public_race_message,
    _race_chat_id, execute_race, get_state, restore_race_deadlines, router,
)
from utils.game_race_utils import GameState, SELECTION_WINDOW
from utils.race_simulation import BOOST_BONUS, HINDER_PENALTY


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


class RaceChoiceTests(unittest.TestCase):
    def test_window_closes_registration_immediately(self):
        race = state()
        self.assertEqual(
            datetime.fromisoformat(race.selection_deadline),
            datetime(2026, 10, 15, 12, 0) + SELECTION_WINDOW,
        )
        with self.assertRaises(ValueError):
            race.add_player(players()[0])
        self.assertFalse(race.deadline_reached(datetime(2026, 10, 15, 12, 9)))
        self.assertTrue(race.deadline_reached(datetime(2026, 10, 15, 12, 10)))

    def test_scaled_targets_and_cleared_selection_on_card_change(self):
        for count, target_count in ((8, 3), (9, 4), (10, 4), (11, 5), (12, 5)):
            race = state(count)
            self.assertEqual(race.target_count(), target_count)
            race.set_wheels(players(count)[0], 1)
            race.choose_action(1, "hinder")
            for target_id in range(2, target_count + 2):
                race.toggle_target(1, target_id)
            self.assertEqual(len(race.actions[1].targets), target_count)
            with self.assertRaises(ValueError):
                race.toggle_target(1, target_count + 2)
            with self.assertRaises(ValueError):
                race.toggle_target(1, 1)
            race.confirm(1)
            self.assertIn(1, race.confirmed)
            race.choose_action(1, "boost")
            self.assertEqual(race.actions[1].targets, ())
            self.assertEqual(race.actions[1].bonus, BOOST_BONUS)
            self.assertNotIn(1, race.confirmed)

    def test_roundtrip_and_lane_mapping(self):
        race = state(8)
        race.choose_action(1, "hinder")
        for target in (2, 3, 4):
            race.toggle_target(1, target)
        race.set_wheels(players()[0], 2)
        race.confirm(1)
        restored = GameState.from_dict(race.to_dict())
        self.assertEqual(restored.to_dict(), race.to_dict())
        self.assertEqual(restored.resolve_actions()[0].targets, (1, 2, 3))
        self.assertEqual(restored.resolve_actions()[0].penalty, HINDER_PENALTY)

    def test_early_start_only_after_everyone_confirms(self):
        race = state()
        for participant in players():
            race.set_wheels(participant, 0)
            race.choose_action(participant.id, "guard")
            race.confirm(participant.id)
        self.assertTrue(race.all_ready())
        race.choose_action(2, "hinder")
        self.assertFalse(race.all_ready())
        race.fill_missing_choices()
        self.assertEqual(race.actions[2].kind, "neutral")

    def test_compact_rich_table_and_inline_cell_buttons(self):
        race = state()
        race.set_wheels(players()[0], 0)
        race.choose_action(1, "hinder")
        panel = _panel_message(race, players()[0], players())
        tables = [block for block in panel.blocks if isinstance(block, InputRichBlockTable)]
        self.assertEqual(len(tables), 3)
        self.assertEqual(len(tables[-1].cells), 8)
        self.assertIsInstance(tables[-1].cells[1][1].text, RichTextButton)
        self.assertTrue(all(table.is_compact for table in tables))
        public = _public_race_message(race, players())
        public_table = next(
            block for block in public.blocks if isinstance(block, InputRichBlockTable)
        )
        self.assertEqual(len(public_table.cells[0]), 4)
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
            race.set_wheels(participant, participant.id % 3)
            race.choose_action(participant.id, "boost")
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
            bot.send_rich_message.assert_awaited_once()
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

    async def test_legacy_state_is_not_treated_as_active_game(self):
        service = Mock()
        service.get_parameter = AsyncMock(return_value=json.dumps({
            "-101": {"player_ids": [1], "wheels": {}, "weather": {}},
        }))
        with patch("handlers.game_race_handlers.ParamService", return_value=service):
            self.assertIsNone(await get_state(-101, Mock()))


if __name__ == "__main__":
    unittest.main()
