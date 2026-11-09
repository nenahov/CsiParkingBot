import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.types import InputRichBlockButtons, InputRichBlockParagraph

from handlers.driver_callback import MyCallback
from handlers.game_race_handlers import (
    RACE_PANEL_STEPS, _next_transfer_picker, _panel_fallback, _panel_keyboard,
    _panel_message, _show_race_panel, _transfer_candidates, race_confirm_callback,
    race_guard_callback, race_pick_callback, race_plan_callback,
    race_step_callback, race_target_callback, race_wheel_callback,
)
from utils.game_race_utils import GameState
from utils.race_simulation import RaceAction

CHAT_ID = -1001234567890


def selection(count=7):
    players = [
        SimpleNamespace(id=index, chat_id=100 + index, title=f"Водитель {index}")
        for index in range(1, count + 1)
    ]
    race = GameState({"1": [2, 3, 5], "2": [3, 4, 3]})
    race.player_ids = [player.id for player in players]
    race.begin_selection(datetime.now(), seed=123)
    return race, players


def complete_choice(race, driver):
    race.set_wheels(driver, 0)
    for slot in range(race.target_count()):
        race.set_transfer(driver.id, slot, "source", 2 + slot)
        race.set_transfer(driver.id, slot, "recipient", 3 + slot)


def buttons(race, driver, players, **kwargs):
    markup = _panel_keyboard(race, driver, players, chat_id=CHAT_ID, **kwargs)
    return [button for row in markup.inline_keyboard for button in row]


def callbacks(race, driver, players, **kwargs):
    return [MyCallback.unpack(button.callback_data)
            for button in buttons(race, driver, players, **kwargs)]


class RaceSelectionScreenTests(unittest.TestCase):
    def setUp(self):
        self.race, self.players = selection()
        self.driver = self.players[0]

    def test_first_screen_only_asks_for_tires(self):
        text = _panel_fallback(self.race, self.driver, self.players)
        self.assertIn("Шаг 1 из 5", text)
        self.assertIn("Какие шины", text)
        self.assertEqual(
            {item.action for item in callbacks(self.race, self.driver, self.players)},
            {"race_wheel", "race_step"},
        )
        self.assertTrue(all(
            len(button.text) > 2 for button in buttons(self.race, self.driver, self.players)
        ))

    def test_reopening_resumes_first_missing_side(self):
        self.race.set_wheels(self.driver, 1)
        self.race.set_transfer(1, 0, "source", 2)
        self.assertEqual(_next_transfer_picker(self.race, 1), "r0")
        text = _panel_fallback(self.race, self.driver, self.players)
        self.assertIn("Маршрут 1 из 3", text)
        self.assertIn("Водитель 2 → кому?", text)
        self.assertIn("Готово маршрутов: 0/3", text)
        targets = [item for item in callbacks(self.race, self.driver, self.players)
                   if item.action == "race_target"]
        self.assertTrue(targets)
        self.assertTrue(all(item.event_type == "r0" for item in targets))
        self.assertNotIn(2, [item.spot_id for item in targets])

    def test_candidates_exclude_self_opposite_and_duplicates_in_same_role(self):
        self.race.actions[1] = RaceAction("nitro", transfers=((2, 3), (4, 5)))
        for picker, expected in (("s0", {2, 5, 6, 7}), ("r0", {3, 4, 6, 7})):
            with self.subTest(picker=picker):
                candidates = _transfer_candidates(
                    self.race, self.driver, self.players, picker,
                )
                self.assertEqual({player.id for player in candidates}, expected)
                # A player may still be chosen in the other role in another route.
                for player in candidates:
                    restored = GameState.from_dict(self.race.to_dict())
                    restored.set_transfer(
                        1, 0, "source" if picker[0] == "s" else "recipient", player.id,
                    )

    def test_summary_has_route_cards_and_no_confirmation_for_incomplete_choice(self):
        self.race.set_transfer(1, 0, "source", 2)
        message = _panel_message(self.race, self.driver, self.players, view="review")
        text = _panel_fallback(self.race, self.driver, self.players, view="review")
        self.assertIn("Водитель 2 → Получатель не выбран", text)
        self.assertNotIn("race_confirm", {
            item.action for item in callbacks(
                self.race, self.driver, self.players, view="review",
            )
        })
        for index, block in enumerate(message.blocks):
            if isinstance(block, InputRichBlockParagraph) and ". " in str(block.text):
                if " → " in str(block.text):
                    self.assertIsInstance(message.blocks[index + 1], InputRichBlockButtons)
        self.assertTrue(all(
            item.bool_value for item in callbacks(
                self.race, self.driver, self.players, view="review",
            ) if item.action == "race_pick"
        ))

    def test_confirmation_is_only_on_ready_summary_and_edits_reset_it(self):
        complete_choice(self.race, self.driver)
        self.assertIsNone(_next_transfer_picker(self.race, 1))
        self.assertIn("race_confirm", {
            item.action for item in callbacks(self.race, self.driver, self.players)
        })
        self.race.confirm(1)
        text = _panel_fallback(self.race, self.driver, self.players)
        self.assertIn("Выбор подтверждён", text)
        self.assertNotIn("race_confirm", {
            item.action for item in callbacks(self.race, self.driver, self.players)
        })
        self.race.set_transfer(1, 0, "source", 7)
        self.assertNotIn(1, self.race.confirmed)
        self.assertIn("Выбор ещё не подтверждён", _panel_fallback(
            self.race, self.driver, self.players,
        ))

    def test_guard_limit_keeps_removal_available_and_defaults_are_explained(self):
        for target in (2, 3, 4):
            self.race.toggle_guard(1, target)
        options = callbacks(self.race, self.driver, self.players, view="guard")
        self.assertEqual(
            {item.spot_id for item in options if item.action == "race_guard"},
            {2, 3, 4},
        )
        text = _panel_fallback(self.race, self.driver, self.players, view="guard")
        self.assertIn("Выбрано: 3/3", text)
        self.assertIn("сначала снимите одну", text)
        self.race.toggle_guard(1, 2)
        self.assertEqual(len([
            item for item in callbacks(self.race, self.driver, self.players, view="guard")
            if item.action == "race_guard"
        ]), 6)
        plan_text = " ".join(button.text for button in buttons(
            self.race, self.driver, self.players, view="plan",
        ))
        self.assertIn("✅ ⚖️ Ровно", plan_text)
        self.assertNotIn("steady", plan_text)

    def test_rich_and_fallback_have_identical_questions_and_buttons(self):
        for count in (7, 9, 12):
            race, players = selection(count)
            for view in RACE_PANEL_STEPS:
                for picker in (None, "s0", f"r{race.target_count() - 1}"):
                    with self.subTest(count=count, view=view, picker=picker):
                        kwargs = dict(view=view, picker=picker, editing=True)
                        rich = _panel_message(race, players[0], players, CHAT_ID, **kwargs)
                        fallback = _panel_fallback(
                            race, players[0], players, CHAT_ID, **kwargs,
                        )
                        rich_buttons = [
                            (button.text, button.callback_data)
                            for block in rich.blocks if isinstance(block, InputRichBlockButtons)
                            for button in block.buttons
                        ]
                        plain_buttons = buttons(race, players[0], players, **kwargs)
                        self.assertEqual(rich_buttons, [
                            (button.text, button.callback_data) for button in plain_buttons
                        ])
                        self.assertIn(rich.blocks[0].text, fallback)
                        for block in rich.blocks[1:]:
                            if isinstance(block, InputRichBlockParagraph):
                                self.assertIn(block.text, fallback)
                        for button in plain_buttons:
                            self.assertLessEqual(len(button.callback_data.encode()), 64)
                            self.assertEqual(
                                MyCallback.unpack(button.callback_data).day_num, CHAT_ID,
                            )


class RaceSelectionCallbackTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.race, self.players = selection()
        self.driver = self.players[0]
        self.callback = SimpleNamespace(
            answer=AsyncMock(),
            message=SimpleNamespace(
                chat=SimpleNamespace(id=self.driver.chat_id, type="private"), bot=AsyncMock(),
            ),
        )
        self.get_state = self.patch("get_state", return_value=self.race)
        self.save = self.patch("save_state")
        self.show = self.patch("_show_race_panel")
        self.refresh = self.patch("_refresh_public_status")
        self.alarm = self.patch("send_alarm")

    def patch(self, name, **kwargs):
        patcher = patch(f"handlers.game_race_handlers.{name}", new_callable=AsyncMock, **kwargs)
        result = patcher.start()
        self.addCleanup(patcher.stop)
        return result

    async def invoke(self, handler, *, action="unused", spot_id=None,
                     event_type=None, editing=None):
        data = MyCallback(
            action=action, user_id=self.driver.chat_id, spot_id=spot_id,
            day_num=CHAT_ID, event_type=event_type, bool_value=editing,
        )
        await handler(self.callback, data, None, self.driver)
        return self.show.await_args

    async def test_full_wizard_automatically_advances_and_confirms(self):
        await self.invoke(race_wheel_callback, spot_id=1)
        self.assertEqual(self.race.wheels["1"], 1)
        for slot in range(3):
            shown = await self.invoke(
                race_target_callback, spot_id=2 + slot, event_type=f"s{slot}",
            )
            self.assertEqual(shown.args[5], f"r{slot}")
            shown = await self.invoke(
                race_target_callback, spot_id=3 + slot, event_type=f"r{slot}",
            )
            self.assertEqual(shown.args[5], f"s{slot + 1}" if slot < 2 else None)
        self.assertEqual(shown.kwargs["view"], "guard")
        shown = await self.invoke(race_guard_callback, spot_id=2)
        self.assertEqual(shown.kwargs["view"], "guard")
        shown = await self.invoke(race_step_callback, event_type="plan")
        self.assertEqual(shown.kwargs["view"], "plan")
        shown = await self.invoke(race_plan_callback, event_type="late")
        self.assertEqual(shown.kwargs["view"], "review")
        self.assertEqual(self.race.actions[1].plan, "late")
        await self.invoke(race_confirm_callback)
        self.assertIn(1, self.race.confirmed)
        self.assertEqual(self.show.await_args.kwargs["view"], "review")
        self.alarm.assert_not_awaited()
        self.assertTrue(all(call.args[0] == CHAT_ID for call in self.save.await_args_list))

    async def test_editing_complete_route_returns_to_summary_without_changing_others(self):
        complete_choice(self.race, self.driver)
        self.race.confirm(1)
        original = self.race.actions[1].transfers
        shown = await self.invoke(
            race_target_callback, spot_id=7, event_type="s0", editing=True,
        )
        self.assertEqual(shown.kwargs["view"], "review")
        self.assertIsNone(shown.args[5])
        self.assertEqual(self.race.actions[1].transfers, ((7, 3), *original[1:]))
        self.assertNotIn(1, self.race.confirmed)

    async def test_editing_empty_route_preserves_context_until_both_sides_selected(self):
        shown = await self.invoke(race_pick_callback, event_type="s0", editing=True)
        self.assertTrue(shown.kwargs["editing"])
        shown = await self.invoke(
            race_target_callback, spot_id=2, event_type="s0", editing=True,
        )
        self.assertEqual(shown.args[5], "r0")
        self.assertTrue(shown.kwargs["editing"])
        shown = await self.invoke(
            race_target_callback, spot_id=3, event_type="r0", editing=True,
        )
        self.assertEqual(shown.kwargs["view"], "review")
        self.assertEqual(len(self.race.actions[1].transfers), 1)

    async def test_recipient_can_be_edited_before_source_from_summary(self):
        shown = await self.invoke(
            race_target_callback, spot_id=3, event_type="r0", editing=True,
        )
        self.assertEqual(shown.args[5], "s0")
        shown = await self.invoke(
            race_target_callback, spot_id=2, event_type="s0", editing=True,
        )
        self.assertEqual(shown.kwargs["view"], "review")

    async def test_navigation_does_not_save_or_reset_confirmation(self):
        complete_choice(self.race, self.driver)
        self.race.confirm(1)
        before = self.race.to_dict()
        for view in RACE_PANEL_STEPS:
            await self.invoke(race_step_callback, event_type=view)
        self.assertEqual(self.race.to_dict(), before)
        self.save.assert_not_awaited()
        self.refresh.assert_not_awaited()

    async def test_stale_invalid_target_is_rejected_without_changing_routes(self):
        complete_choice(self.race, self.driver)
        before = self.race.to_dict()
        await self.invoke(race_target_callback, spot_id=4, event_type="s0")
        self.assertEqual(self.race.to_dict(), before)
        self.save.assert_not_awaited()
        self.show.assert_not_awaited()
        self.alarm.assert_awaited_once()

    async def test_navigation_rejects_unknown_steps_closed_window_and_outsiders(self):
        await self.invoke(race_step_callback, event_type="unknown")
        self.race.phase = "running"
        await self.invoke(race_step_callback, event_type="review")
        self.race.phase = "selection"
        self.race.player_ids.remove(self.driver.id)
        await self.invoke(race_step_callback, event_type="review")
        self.assertEqual(self.alarm.await_count, 3)
        self.show.assert_not_awaited()


class RaceSelectionDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_current_step_stays_personal_for_group_and_private_fallback(self):
        race, players = selection()
        race.set_transfer(1, 0, "source", 2)
        service = SimpleNamespace(get_by_id=AsyncMock(
            side_effect=lambda player_id: players[player_id - 1],
        ))
        for chat_type, ephemeral, expected in (
                ("group", None, "answer_rich"),
                ("private", None, "edit_rich"),
                ("group", "secret", "edit_rich"),
        ):
            with self.subTest(chat_type=chat_type, ephemeral=ephemeral):
                callback = SimpleNamespace(message=SimpleNamespace(
                    chat=SimpleNamespace(type=chat_type),
                    ephemeral_message_id=ephemeral,
                ))
                with (
                    patch("handlers.game_race_handlers.DriverService", return_value=service),
                    patch("handlers.game_race_handlers.answer_rich", new_callable=AsyncMock) as answer,
                    patch("handlers.game_race_handlers.edit_rich", new_callable=AsyncMock) as edit,
                ):
                    await _show_race_panel(
                        callback, race, players[0], None, CHAT_ID, picker="r0",
                    )
                called, unused = (answer, edit) if expected == "answer_rich" else (edit, answer)
                unused.assert_not_awaited()
                kwargs = called.await_args.kwargs
                self.assertTrue(kwargs["personal"])
                self.assertIn("Водитель 2 → кому?", kwargs["fallback_text"])
                self.assertTrue(kwargs["fallback_reply_markup"].inline_keyboard)


if __name__ == "__main__":
    unittest.main()
