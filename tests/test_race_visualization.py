"""Проверки прямой мультяшной трассы без изменения результатов заезда."""

import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from utils.cars_generator import (
    NITRO_GLOW_FRAMES, PODIUM_COLORS, RACE_FOOTER_HEIGHT, RACE_HUD_HEIGHT,
    RACE_LANE_HEIGHT, RACE_TRACK_LENGTH, _display_position, _draw_car_number,
    _draw_race_hud, _make_car_shadow, _nitro_intensity, _race_order,
    _render_race_frame, create_race_gif, draw_nitro_flame, draw_race_track,
    get_car, main,
)
from utils.game_race_utils import GameState
from utils.race_simulation import initial_nitro, resolve_race_simulation


def racers(count):
    """Собрать участников с разными существующими спрайтами."""
    return [
        SimpleNamespace(id=i + 1, title=f"Водитель {i + 1}",
                        attributes={"car_index": i})
        for i in range(count)
    ]


class RaceVisualizationTests(unittest.TestCase):
    """Геометрия, опознаваемость и совпадение видео с симуляцией."""

    def test_number_is_centered_on_car_without_badge(self):
        frame = Image.new("RGBA", (160, 90), (0, 0, 0, 0))
        _draw_car_number(frame, 20, 20, (100, 50), 12)
        bbox = frame.getbbox()
        self.assertIsNotNone(bbox)
        self.assertGreaterEqual(bbox[0], 48)
        self.assertLessEqual(bbox[2], 92)
        self.assertGreaterEqual(bbox[1], 25)
        self.assertLessEqual(bbox[3], 65)
        self.assertEqual(frame.getpixel((20 + 78, 20 - 6))[3], 0)

    def test_podium_uses_three_medal_colors(self):
        frame = Image.new("RGBA", (1800, 500))
        result = SimpleNamespace(
            position_at=lambda idx, frame_index: 100 - idx,
            finish_frames=None, frame_count=10, winners=[0, 1, 2],
        )
        _draw_race_hud(frame, racers(3), result, 3, "race", 0)
        for place, color in enumerate(PODIUM_COLORS):
            left = 340 + place * 460
            pixels = [
                frame.getpixel((x, y))[:3]
                for x in range(left + 18, left + 39)
                for y in range(25, 50)
            ]
            self.assertIn(color, pixels)

    def test_nitro_visual_lasts_longer_and_motion_eases_without_changing_result(self):
        pulses = (5,)
        self.assertEqual(_nitro_intensity(pulses, 5), 1)
        self.assertGreater(_nitro_intensity(pulses, 15), 0)
        self.assertEqual(_nitro_intensity(pulses, 5 + NITRO_GLOW_FRAMES), 0)
        result = SimpleNamespace(
            position_at=lambda idx, frame: frame * 2 + (8 if frame >= 5 else 0),
            frame_count=15, finish_frames=[8],
        )
        self.assertLess(
            _display_position(result, 0, 5) - _display_position(result, 0, 4),
            result.position_at(0, 5) - result.position_at(0, 4),
        )
        self.assertEqual(_display_position(result, 0, 12),
                         result.position_at(0, 8))

    def test_nitro_is_local_underglow_not_a_road_trail(self):
        base = Image.new("RGBA", (220, 90), (75, 75, 75, 255))
        strong = base.copy()
        fading = base.copy()
        draw_nitro_flame(strong, 60, 20, (100, 50))
        draw_nitro_flame(fading, 60, 20, (100, 50), intensity=.25)
        # Под кормой есть свет и короткая струя, но далеко за машиной
        # асфальт не окрашивается.
        self.assertGreater(strong.getpixel((54, 45))[2], 75)
        self.assertGreater(strong.getpixel((30, 45))[2], 75)
        self.assertEqual(strong.getpixel((5, 45)), base.getpixel((5, 45)))
        self.assertGreater(strong.getpixel((54, 45))[2],
                           fading.getpixel((54, 45))[2])

    def test_demo_main_uses_real_nitro_simulation(self):
        with patch("utils.cars_generator.create_race_gif") as render:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                result = main()
        self.assertEqual(len(result.winners), 9)
        self.assertEqual(sum(result.nitro), 9 * initial_nitro(9))
        self.assertGreater(len(set(result.nitro)), 1)
        self.assertTrue(all(len(pulses) == amount for pulses, amount
                            in zip(result.nitro_pulses, result.nitro)))
        self.assertIn("race_demo.mp4", output.getvalue())
        self.assertIs(render.call_args.kwargs["simulation_result"], result)
        self.assertIsNone(render.call_args.kwargs["output_path"])

    def test_finished_car_keeps_its_place_on_dashboard(self):
        result = SimpleNamespace(
            winners=[0, 1, 2], finish_frames=[5, 8, None],
            position_at=lambda idx, frame: (1700, 2000, 2100)[idx],
        )
        self.assertEqual(_race_order(result, 3, 6), [0, 2, 1])
        self.assertEqual(_race_order(result, 3, 9), [0, 1, 2])

    def test_track_and_badges_fit_seven_and_twelve_lanes(self):
        for count in (7, 12):
            with self.subTest(count=count):
                players = racers(count)
                track = draw_race_track(players, track_length=RACE_TRACK_LENGTH)
                self.assertEqual(track.size, (RACE_TRACK_LENGTH,
                                              count * RACE_LANE_HEIGHT))
                cars = [get_car(i).rotate(270, expand=True)
                        for i in range(count)]
                shadows = [_make_car_shadow(car) for car in cars]
                result = SimpleNamespace(
                    position_at=lambda idx, frame: 150 + idx * 30 + frame * 10,
                    nitro_pulses=None, frame_count=10,
                    winners=list(range(count)),
                )
                frame = _render_race_frame(
                    track.convert("RGBA"), cars, shadows, players, result, 3)
                self.assertEqual(
                    frame.size,
                    (RACE_TRACK_LENGTH,
                     count * RACE_LANE_HEIGHT + RACE_HUD_HEIGHT + RACE_FOOTER_HEIGHT),
                )

    def test_mp4_uses_the_same_simulation_and_skips_unused_gif(self):
        players = racers(7)
        game = GameState({"1": [10, 0, 0], "2": [10, 0, 0]})
        result = resolve_race_simulation(
            players, [0] * 7, game.weather, {}, seed=17,
            frame_count=4, track_distance=RACE_TRACK_LENGTH - 100, car_width=100,
        )
        original_dir = Path.cwd()
        with tempfile.TemporaryDirectory() as output_dir:
            try:
                os.chdir(output_dir)
                winners = create_race_gif(
                    game, players, 123, output_path=None, frame_count=4,
                    simulation_result=result,
                )
                self.assertEqual(winners, result.winners)
                self.assertGreater(Path("race_123.mp4").stat().st_size, 1000)
                self.assertFalse(Path("race_123.gif").exists())
                create_race_gif(
                    game, players, 124, output_path="race_124.gif",
                    frame_count=4, simulation_result=result,
                )
                self.assertGreater(Path("race_124.gif").stat().st_size, 1000)
            finally:
                os.chdir(original_dir)
