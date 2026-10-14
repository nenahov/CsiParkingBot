import random
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from utils.game_parking_city_generator import (
    ROADBLOCKS,
    generate_city_map_with_constraints,
)
from utils.game_parking_utils import (
    CAR,
    EMPTY,
    FINISH,
    FUEL,
    STONE,
    TREASURE,
    WALLS,
    GameState,
    can_reach_finish_with_fuel,
    generate_map_with_constraints,
    is_path_exists,
)


class ParkingGameUtilsTests(unittest.TestCase):
    def test_no_movement_after_win_or_loss(self):
        state = GameState(0, 0, 1, 0, 0, [[CAR, FINISH], [EMPTY, EMPTY]])
        self.assertEqual(state.move(0, 1), FINISH)
        self.assertTrue(state.is_win())
        self.assertIsNone(state.move(0, -1))
        self.assertEqual((state.x, state.y, state.fuel), (0, 1, 1))

        lost = GameState(0, 0, 0, 0, 0, [[CAR, FUEL], [EMPTY, EMPTY]])
        self.assertIsNone(lost.move(0, 1))
        self.assertEqual(lost.map_matrix[0][1], FUEL)

    def test_only_one_cell_cardinal_moves_are_allowed(self):
        state = GameState(0, 0, 50, 0, 0, [[CAR, EMPTY, FINISH]])
        for dx, dy in ((0, 0), (0, 2), (1, 1), (-1, 0)):
            self.assertTrue(state.is_wall(dx, dy))
            self.assertIsNone(state.move(dx, dy))
        self.assertEqual(state.fuel, 50)

    def test_path_search_handles_missing_symbols_and_unreachable_bonus(self):
        self.assertFalse(is_path_exists([]))
        self.assertFalse(is_path_exists([[EMPTY]]))
        grid = [
            [CAR, FINISH, WALLS[1]],
            [WALLS[1], WALLS[1], WALLS[1]],
            [EMPTY, EMPTY, TREASURE],
        ]
        self.assertTrue(is_path_exists(grid))
        self.assertFalse(is_path_exists(grid, TREASURE))
        self.assertTrue(is_path_exists([[CAR, FINISH, TREASURE]], TREASURE))
        self.assertFalse(is_path_exists(
            [[CAR, FINISH, TREASURE]], TREASURE, forbidden=(FINISH,)
        ))

    def test_fuel_check_accounts_for_stones_and_one_time_refueling(self):
        road = [[STONE] for _ in range(16)]
        road[0][0], road[-1][0] = CAR, FINISH
        self.assertTrue(is_path_exists(road))
        self.assertFalse(can_reach_finish_with_fuel(road))

        road = [[EMPTY] for _ in range(60)]
        road[0][0], road[-1][0] = CAR, FINISH
        self.assertFalse(can_reach_finish_with_fuel(road))
        road[30][0] = FUEL
        self.assertTrue(can_reach_finish_with_fuel(road))

    def test_generated_maps_have_reachable_bonus_and_winnable_finish(self):
        with patch("utils.game_parking_utils.random", random.Random(42)):
            for _ in range(100):
                state = generate_map_with_constraints(17, 13)
                self.assertTrue(is_path_exists(
                    state.map_matrix, TREASURE, forbidden=(FINISH,)
                ))
                self.assertTrue(can_reach_finish_with_fuel(state.map_matrix))

    def test_single_distant_finish_does_not_crash_treasure_selection(self):
        state = generate_map_with_constraints(2, 2, wall_ratio=0, min_distance=2)
        self.assertTrue(is_path_exists(state.map_matrix, TREASURE))

    def test_invalid_parameters_raise_value_error(self):
        for kwargs in (
                {"n": 0, "m": 13},
                {"n": 1, "m": 1, "min_distance": 0},
                {"n": 17, "m": 13, "wall_ratio": -0.1},
                {"n": 17, "m": 13, "fuel_ratio": 2},
                {"n": 17, "m": 13, "max_attempts": 0},
                {"n": 17, "m": 13, "wall_ratio": 1},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                generate_map_with_constraints(**kwargs)

    def test_city_generator_keeps_buildings_off_the_streets(self):
        with patch("utils.game_parking_city_generator.random", random.Random(7)):
            state = generate_city_map_with_constraints(
                17, 13, street_step=3, blocked_ratio=0
            )

        self.assertTrue(is_path_exists(state.map_matrix, TREASURE, forbidden=(FINISH,)))
        self.assertTrue(can_reach_finish_with_fuel(state.map_matrix))
        for x in range(17):
            for y in range(13):
                is_street = x % 3 == 0 or y % 3 == 0
                if not is_street:
                    self.assertIn(state.map_matrix[x][y], WALLS)

    def test_city_generator_places_closures_only_on_streets(self):
        with patch("utils.game_parking_city_generator.random", random.Random(11)):
            state = generate_city_map_with_constraints(
                17, 13, street_step=3, blocked_ratio=0.2
            )

        blocked_on_street = 0
        for x in range(17):
            for y in range(13):
                if state.map_matrix[x][y] in ROADBLOCKS:
                    self.assertNotEqual(x % 3 == 0, y % 3 == 0)
                    blocked_on_street += 1
        road_count = sum(x % 3 == 0 or y % 3 == 0
                         for x in range(17) for y in range(13))
        self.assertEqual(blocked_on_street, int(0.2 * road_count))

    def test_city_generator_validates_street_parameters(self):
        with self.assertRaises(ValueError):
            generate_city_map_with_constraints(17, 13, street_step=0)
        with self.assertRaises(ValueError):
            generate_city_map_with_constraints(17, 13, street_step=3, street_width=4)
        with self.assertRaises(ValueError):
            generate_city_map_with_constraints(3, 3, street_step=3, blocked_ratio=1)


class ParkingGameHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_stale_callback_does_not_pay_out_twice(self):
        from handlers.game_parking_handlers import move_callback

        state = GameState(0, 0, 1, 0, 0, [[CAR, FINISH], [EMPTY, EMPTY]])
        driver = SimpleNamespace(
            id=1, title="Игрок", attributes={"karma": 2},
            get_karma=lambda: driver.attributes["karma"],
        )
        callback = SimpleNamespace(
            message=SimpleNamespace(edit_text=AsyncMock()),
            answer=AsyncMock(),
        )
        direction = SimpleNamespace(spot_id=0, day_num=1)
        with (
            patch("handlers.game_parking_handlers.get_state", return_value=state),
            patch("handlers.game_parking_handlers.save_state") as save,
            patch("handlers.game_parking_handlers.send_alarm", new_callable=AsyncMock),
            patch("handlers.game_parking_handlers.AuditService") as audit,
        ):
            audit.return_value.log_action = AsyncMock()
            await move_callback(callback, direction, None, driver, None)
            await move_callback(callback, direction, None, driver, None)
            self.assertEqual(driver.attributes["karma"], 3)
            self.assertEqual(audit.return_value.log_action.await_count, 2)
            save.assert_called_once()
            callback.answer.assert_awaited_once_with("Игра уже завершена")


if __name__ == "__main__":
    unittest.main()
