import random
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from PIL import Image

from handlers.game_race_handlers import (
    _nitro_rich_message, _panel_keyboard, _panel_message,
    _public_race_message, _result_rich_message, restore_race_deadlines,
)
from scripts.race_nitro_balance import random_actions
from utils.cars_generator import draw_nitro_flame
from utils.game_race_utils import GameState, SELECTION_WINDOW
from utils.race_simulation import (
    RaceAction, initial_nitro, resolve_nitro, resolve_race_simulation,
)

FORECAST = {"1": [0, 0, 10], "2": [0, 0, 10]}


def racers(count):
    return [SimpleNamespace(id=i + 1, chat_id=100 + i, title=f"Водитель {i + 1}")
            for i in range(count)]


def text_of(message):
    return repr(message.model_dump(exclude_none=True))


class NitroTransferTests(unittest.TestCase):
    def test_blocked_delivery_returns_three_stolen_charges(self):
        actions = {
            0: RaceAction("nitro", transfers=((1, 4), (2, 5), (3, 6))),
            4: RaceAction("nitro", guards=(0,)),
            5: RaceAction("nitro", guards=(0,)),
            6: RaceAction("nitro", guards=(0,)),
        }
        reserve, ledger = resolve_nitro(7, actions, 123)
        self.assertEqual(reserve[0], 8)
        self.assertEqual(sum(reserve), 35)
        self.assertEqual(len(ledger), 3)
        self.assertTrue(all(entry["delivered_to"] == 0 for entry in ledger))

    def test_blocked_theft_is_paid_from_actors_reserve(self):
        actions = {
            0: RaceAction("nitro", transfers=((1, 2),)),
            1: RaceAction("nitro", guards=(0,)),
        }
        reserve, _ = resolve_nitro(7, actions, 2)
        self.assertEqual(reserve[:3], [4, 5, 6])

    def test_all_attack_one_respects_supply_and_conserves_nitro(self):
        actions = {
            i: RaceAction("nitro", transfers=((11, (i + 1) % 11),))
            for i in range(11)
        }
        reserve, ledger = resolve_nitro(12, actions, 8)
        self.assertEqual(reserve[11], 0)
        self.assertEqual(sum(reserve), 12 * initial_nitro(12))
        self.assertTrue(all(value >= 0 for value in reserve))
        self.assertEqual((reserve, ledger), resolve_nitro(12, actions, 8))

    def test_protection_leaves_one_of_seven_nitro(self):
        actions = {
            i: RaceAction("nitro", transfers=((11, (i + 1) % 11),))
            for i in range(11)
        }
        actions[11] = RaceAction("nitro", guards=tuple(range(5)))
        reserve, _ = resolve_nitro(12, actions, 8)
        self.assertEqual(reserve[11], 1)

    def test_seven_racers_three_protections_leave_two(self):
        actions = {
            i: RaceAction("nitro", transfers=((6, (i + 1) % 6),))
            for i in range(6)
        }
        actions[6] = RaceAction("nitro", guards=(0, 1, 2))
        reserve, _ = resolve_nitro(7, actions, 9)
        self.assertEqual(reserve[6], 2)

    def test_randomized_legal_choices_never_create_nitro_or_debt(self):
        rng = random.Random(121)
        for count in range(7, 13):
            for _ in range(100):
                reserve, _ = resolve_nitro(
                    count, random_actions(count, rng), rng.randrange(2 ** 31),
                )
                self.assertEqual(sum(reserve), count * initial_nitro(count))
                self.assertTrue(all(value >= 0 for value in reserve))

    def test_invalid_pairs_and_guards_are_rejected(self):
        bad = [
            RaceAction("nitro", transfers=((0, 2),)),
            RaceAction("nitro", transfers=((1, 1),)),
            RaceAction("nitro", transfers=((1, 2), (1, 3))),
            RaceAction("nitro", guards=(1, 1)),
            RaceAction("nitro", plan="unknown"),
        ]
        for action in bad:
            with self.subTest(action=action), self.assertRaises(ValueError):
                resolve_nitro(7, {0: action}, 1)

    def test_nitro_activations_and_results_are_reproducible(self):
        actions = {i: RaceAction("nitro", plan=("early", "steady", "late")[i % 3])
                   for i in range(8)}
        args = (range(8), [0] * 8, FORECAST, actions, 17)
        result = resolve_race_simulation(*args)
        again = resolve_race_simulation(*args)
        self.assertEqual(result.spans, again.spans)
        self.assertEqual(result.winners, again.winners)
        self.assertEqual(result.nitro, [5] * 8)
        for index, starts in enumerate(result.nitro_pulses):
            self.assertEqual(len(starts), result.nitro[index])
            self.assertTrue(all(start < result.finish_frames[index] for start in starts))
            self.assertTrue(all(span.speed > 0 for span in result.spans[index]))

    def test_forecast_can_reverse_early_vs_late_plan(self):
        actions = {
            i: RaceAction("nitro", plan=("early" if i % 2 == 0 else "late"))
            for i in range(8)
        }
        sunny_start = resolve_race_simulation(
            range(8), [0] * 8,
            {"1": [0, 0, 10], "2": [0, 10, 0]}, actions, 17,
        )
        sunny_later = resolve_race_simulation(
            range(8), [0] * 8,
            {"1": [0, 10, 0], "2": [0, 0, 10]}, actions, 17,
        )
        self.assertEqual(sunny_start.winners[0] % 2, 0)
        self.assertEqual(sunny_later.winners[0] % 2, 1)


class NitroStateAndPrivacyTests(unittest.TestCase):
    def test_selection_validation_timeout_and_migration(self):
        race = GameState(FORECAST)
        race.player_ids = list(range(1, 8))
        race.begin_selection(datetime(2026, 10, 26, 9), 4)
        race.set_wheels(racers(7)[0], 1)
        race.choose_plan(1, "late")
        race.set_transfer(1, 2, "source", 2)
        self.assertFalse(race.ready(1))
        race.toggle_guard(1, 3)
        race.fill_missing_choices()
        self.assertEqual(race.actions[1].transfers, ())
        self.assertEqual(race.wheels["1"], 1)
        old = race.to_dict()
        old.pop("rules_version")
        old["actions"] = {"1": {"kind": "guard"}}
        old["confirmed"] = [1]
        migrated = GameState.from_dict(old)
        self.assertTrue(migrated.migrate_legacy_selection(datetime(2026, 10, 26, 10)))
        self.assertEqual(migrated.selection_deadline,
                         (datetime(2026, 10, 26, 10) + SELECTION_WINDOW).isoformat())
        self.assertEqual(migrated.confirmed, set())
        self.assertEqual(migrated.actions, {})

    def test_public_messages_never_reveal_routes_or_private_plan(self):
        people = racers(7)
        race = GameState(FORECAST)
        race.player_ids = list(range(1, 8))
        race.begin_selection(datetime(2026, 10, 26, 9), 4)
        race.actions[1] = RaceAction("nitro", transfers=((1 + 1, 3),),
                                     guards=(4,), plan="late")
        public = _public_race_message(race, people)
        simulation = resolve_race_simulation(
            people, [0] * 7, FORECAST, {0: RaceAction("nitro")}, 4,
        )
        reserves = _nitro_rich_message(simulation, people)
        for message in (public, reserves):
            rendered = text_of(message)
            self.assertNotIn("source", rendered)
            self.assertNotIn("recipient", rendered)
            self.assertNotIn("late", rendered)
        private = _panel_message(race, people[0], people)
        self.assertIn("Забрать у", text_of(private))
        result = _result_rich_message(simulation, people, race)
        self.assertNotIn("source", text_of(result))
        self.assertNotIn("recipient", text_of(result))

    def test_picker_fallback_callbacks_fit_telegram_limit(self):
        people = racers(12)
        race = GameState(FORECAST)
        race.player_ids = list(range(1, 13))
        race.begin_selection(datetime(2026, 10, 26, 9), 5)
        keyboard = _panel_keyboard(race, people[0], people,
                                   chat_id=-1001234567890, picker="r4")
        self.assertTrue(all(
            len(button.callback_data.encode()) <= 64
            for row in keyboard.inline_keyboard for button in row
        ))

    def test_flame_is_blue_under_rear_bumper(self):
        frame = Image.new("RGBA", (160, 70), (90, 90, 90, 255))
        draw_nitro_flame(frame, 40, 10, (100, 50))
        red, green, blue, _ = frame.getpixel((34, 35))
        self.assertGreater(blue, red)
        self.assertGreater(blue, green)


class LegacyMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_old_selection_reopens_and_notifies_without_losing_tires(self):
        old = GameState(FORECAST)
        old.player_ids = list(range(1, 8))
        old.begin_selection(datetime(2026, 10, 25, 12), 5)
        old.wheels["1"] = 2
        stored = old.to_dict()
        stored.pop("rules_version")
        stored["actions"] = {"1": {"kind": "guard"}}
        stored["confirmed"] = [1]
        service = Mock()
        service.get_parameter = AsyncMock(return_value=__import__("json").dumps({
            "-100": stored,
        }))
        service.set_parameter = AsyncMock()
        session = AsyncMock()
        bot = AsyncMock()
        scheduler = Mock()
        with (patch("handlers.game_race_handlers.ParamService",
                    return_value=service),
              patch("handlers.game_race_handlers._race_scheduler", scheduler)):
            await restore_race_deadlines(bot, session)
        saved = __import__("json").loads(service.set_parameter.await_args.args[1])["-100"]
        self.assertEqual(saved["wheels"]["1"], 2)
        self.assertEqual(saved["actions"], {})
        self.assertEqual(saved["confirmed"], [])
        self.assertEqual(saved["rules_version"], "nitro-transfer-1")
        session.commit.assert_awaited_once()
        bot.send_message.assert_awaited_once()
        scheduler.add_job.assert_called_once()


if __name__ == "__main__":
    unittest.main()
