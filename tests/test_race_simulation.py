import csv
import importlib.util
import json
import math
import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

_script = Path(__file__).resolve().parents[1] / "scripts" / "race_strategy_simulation.py"
_spec = importlib.util.spec_from_file_location("race_strategy_simulation", _script)
race_tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(race_tool)
from utils.race_simulation import (
    RACE_ENTRY_FEE, SPEED_RANGES, RaceAction, _resolve_actions, allocate_prizes,
    resolve_race_simulation,
)

FORECAST = {"1": [2, 4, 4], "2": [3, 3, 4]}


class RaceSimulationTests(unittest.TestCase):
    def test_prize_pool_is_exact_for_all_supported_sizes(self):
        for n in range(7, 13):
            prizes = allocate_prizes(n)
            self.assertEqual(sum(prizes.values()), n * RACE_ENTRY_FEE)
            self.assertEqual(prizes[n], RACE_ENTRY_FEE)
            self.assertEqual(set(prizes), {1, 2, 3, 4, 5, n})

    def test_speed_ranges_match_original_race(self):
        self.assertEqual(SPEED_RANGES[1][1], (.4, .8))
        self.assertEqual(SPEED_RANGES[2][2], (.3, .7))
        self.assertEqual(SPEED_RANGES[0][0], (.15, .4))

    def test_deterministic_and_renderer_reads_same_positions(self):
        kwargs = dict(
            players=range(8), wheels=[0, 1, 2, 0, 1, 2, 0, 1],
            weather_forecast=FORECAST, actions={0: RaceAction("boost")},
            seed=834,
        )
        first = resolve_race_simulation(**kwargs)
        second = resolve_race_simulation(**kwargs)
        self.assertEqual(first.winners, second.winners)
        self.assertEqual(first.spans, second.spans)
        self.assertEqual(first.weather_segments, second.weather_segments)
        self.assertEqual(first.events, second.events)
        self.assertGreater(first.position_at(0, 1), first.position_at(0, 0))
        self.assertEqual(len(first.winners), 8)
        self.assertEqual(set(first.winners), set(range(8)))

    def test_event_driven_motion_matches_frame_by_frame_rules(self):
        result = resolve_race_simulation(
            range(4), [0, 1, 2, 1], FORECAST, {}, 95,
            frame_count=400, track_distance=1700, car_width=100,
        )
        for racer, tire in enumerate(result.wheels):
            rng = random.Random((95 ^ 0x5EED) + racer * 1_000_003)
            position = 0.0
            factor = 1.0
            speed = 1800 / 400
            bonus = -1001.0
            for frame in range(result.finish_frames[racer] + 1):
                previous = int(3 * position // 1700)
                position += speed
                current = int(3 * position // 1700)
                if previous != current or bonus < -1000:
                    segment = min(current, 2)
                    low, high = SPEED_RANGES[result.weather_segments[segment]][tire]
                    bonus = rng.uniform(low, high)
                    factor += current * rng.uniform(0, .02)
                    speed = 1800 * (factor + bonus) / 400
                self.assertTrue(
                    math.isclose(result.position_at(racer, frame), position,
                                 rel_tol=1e-11, abs_tol=1e-9),
                    f"racer={racer}, frame={frame}",
                )

    def test_guard_reduces_every_attack_without_blocking(self):
        actions = {
            0: RaceAction("hinder", targets=(2, 3)),
            1: RaceAction("hinder", targets=(2,)),
            2: RaceAction("guard"),
        }
        args = dict(players=range(4), wheels=[0] * 4,
                    weather_forecast=FORECAST, actions=actions, seed=123)
        result = resolve_race_simulation(**args)
        self.assertEqual(
            [e["status"] for e in result.events
             if e["kind"] == "hinder" and e["target"] == 2],
            ["reduced", "reduced"],
        )
        self.assertEqual(
            sum(e["status"] == "success" for e in result.events
                if e["kind"] == "hinder" and e["target"] == 3), 1,
        )
        target_two = [
            e for e in result.events
            if e["kind"] == "hinder" and e["target"] == 2
        ]
        self.assertTrue(all(e["guarded"] for e in target_two))
        self.assertTrue(all(e["penalty_applied"] == .05 for e in target_two))

        three_attacks = resolve_race_simulation(
            range(5), [0] * 5, FORECAST,
            {
                0: RaceAction("hinder", targets=(4,)),
                1: RaceAction("hinder", targets=(4,)),
                2: RaceAction("hinder", targets=(4,)),
                4: RaceAction("guard"),
            },
            123,
        )
        target_three = [
            e for e in three_attacks.events
            if e["kind"] == "hinder" and e["target"] == 4
        ]
        self.assertEqual(sum(e["status"] == "reduced" for e in target_three), 3)
        self.assertTrue(all(e["penalty_applied"] > 0 for e in target_three))
        for absorption in (.5, .7, .8):
            with self.subTest(absorption=absorption):
                rng = Mock()
                rng.randrange.return_value = 0
                modifiers, events = _resolve_actions(
                    rng, 4,
                    {
                        0: RaceAction("hinder", (3,)),
                        1: RaceAction("hinder", (3,)),
                        2: RaceAction("hinder", (3,)),
                        3: RaceAction("guard"),
                    },
                    guard_absorption=absorption,
                    hinder_segment_mode="shared",
                )
                self.assertAlmostEqual(
                    modifiers[3][0], -3 * .10 * (1 - absorption),
                )
                self.assertEqual([e["status"] for e in events], ["reduced"] * 3)
                self.assertTrue(all(e["penalty_applied"] > 0 for e in events))

    def test_multiple_attacks_stack(self):
        result = resolve_race_simulation(
            range(4), [0] * 4, FORECAST,
            {0: RaceAction("hinder", (3,)),
             1: RaceAction("hinder", (3,)),
             2: RaceAction("hinder", (3,))}, 117,
        )
        statuses = [e["status"] for e in result.events
                    if e["kind"] == "hinder"]
        self.assertEqual(statuses, ["success", "success", "success"])
        # Check the speed modifiers too, not only the event log.
        rng = Mock()
        rng.randrange.return_value = 0
        modifiers, _ = _resolve_actions(
            rng, 4,
            {actor: RaceAction("hinder", (3,)) for actor in range(3)},
            guard_absorption=0.5, hinder_segment_mode="shared",
        )
        self.assertAlmostEqual(modifiers[3][0], -.30)
        self.assertEqual(modifiers[3][1:], [0.0, 0.0])

    def test_mass_attack_does_not_reverse_car(self):
        result = resolve_race_simulation(
            range(12), [0] * 12, FORECAST,
            {actor: RaceAction("hinder", (11,)) for actor in range(11)}, 117,
        )
        self.assertEqual(
            sum(event["status"] == "success" for event in result.events), 11,
        )
        self.assertTrue(all(span.speed > 0 for span in result.spans[11]))

    def test_invalid_target_and_duplicate_are_rejected(self):
        for targets in ((0,), (1, 1), (99,)):
            with self.subTest(targets=targets):
                with self.assertRaises(ValueError):
                    resolve_race_simulation(
                        range(3), [0] * 3, FORECAST,
                        {0: RaceAction("hinder", targets)}, 123,
                    )

    def test_absent_tire_can_set_final_weather(self):
        result = resolve_race_simulation(
            range(8), [0] * 8, FORECAST, {}, 1,
        )
        self.assertIn(result.weather_segments[-1], (1, 2))

    def test_shared_and_independent_segments(self):
        for segment_mode in ("shared", "independent"):
            result = resolve_race_simulation(
                range(6), [0] * 6, FORECAST,
                {0: RaceAction("hinder", (1, 2, 3, 4, 5))}, 19,
                hinder_segment_mode=segment_mode,
            )
            segments = [e["segment"] for e in result.events]
            self.assertEqual(len(segments), 5)
            if segment_mode == "shared":
                self.assertEqual(len(set(segments)), 1)


class StrategyReportTests(unittest.TestCase):
    def test_target_count_is_capped_and_targets_are_unique(self):
        wheels = [0] * 8
        for policy in ("random", "strongest", "upper_half"):
            targets = race_tool.pick_targets(0, 20, wheels, FORECAST, policy, random.Random(2))
            self.assertEqual(len(targets), 7)
            self.assertEqual(len(set(targets)), 7)
            self.assertNotIn(0, targets)

    def test_population_and_focal_choice(self):
        actions = race_tool.build_actions(
            "hinder_5_10", 8, [0] * 8, FORECAST, "random", "all_guard",
            random.Random(2), 3, .10, .12,
        )
        self.assertEqual(len(actions[0].targets), 5)
        self.assertTrue(all(actions[i].kind == "guard" for i in range(1, 8)))

    def test_guard_absorption_accepts_multiple_values(self):
        args = race_tool.parse_args([
            "--runs", "1", "--players", "8", "--target-policy", "random",
            "--guard-absorption", "0.5,0.7,0.8", "--population", "neutral",
        ])
        self.assertEqual(args.guard_absorptions, [.5, .7, .8])

    def test_csv_json_and_summary_match(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "balance"
            rows, report = race_tool.main([
                "--runs", "10", "--players", "8,10,12", "--seed", "73",
                "--strategies", "neutral,boost_5,hinder_3_10",
                "--target-policy", "random", "--guard-absorption", "0.5",
                "--population", "neutral", "--sample-races", "1",
                "--output", str(output),
            ])
            with output.with_suffix(".csv").open(encoding="utf-8-sig", newline="") as stream:
                csv_rows = list(csv.DictReader(stream))
            disk_report = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
            self.assertEqual(len(rows), 9)
            self.assertEqual({row["players"] for row in rows}, {8, 10, 12})
            self.assertEqual(disk_report, json.loads(json.dumps(report)))
            self.assertEqual(report["rules"]["entry_fee"], 50)
            self.assertEqual(report["rules"]["guard_absorption"], .5)
            self.assertIn("version", report["rules"])
            self.assertEqual(
                report["rules"]["strategy_parameters"]["hinder_3_10"]["targets"], 3,
            )
            for actual, csv_row, scenario in zip(rows, csv_rows, report["scenarios"]):
                self.assertEqual(actual, scenario["summary"])
                self.assertAlmostEqual(float(csv_row["mean_prize"]), actual["mean_prize"])
                self.assertEqual(sum(scenario["rank_histogram"].values()), 10)
            second, _ = race_tool.run_scenario(
                n=8, strategy="boost_5", policy="random",
                population="neutral", segment_mode="shared",
                runs=10, seed=73, opponent_hinder_targets=3,
                opponent_hinder_penalty=.10, opponent_boost=.12,
            )
            self.assertEqual(
                next(row for row in rows if row["players"] == 8
                     and row["strategy"] == "boost_5"),
                second,
            )


if __name__ == "__main__":
    unittest.main()
