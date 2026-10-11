import asyncio
import math
import tempfile
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from PIL import Image

from handlers.map_handlers import build_map_message
from models.parking_spot import SpotStatus
from utils.map_generator import (
    GARBAGE_TRUCK_ROUTE,
    GARBAGE_TRUCK_STEP,
    QUEUE_SPOT_COUNT,
    QUEUE_SPOT_X,
    QUEUE_SPOT_Y,
    SPOT_HEIGHT,
    SPOT_WIDTH,
    _draw_queue_spot_markings,
    _draw_temperature,
    generate_parking_map,
    get_spot_layout,
    _queue_cars,
    _spot_size,
    add_garbage_truck,
    garbage_truck_frames,
)
from utils.weather_generator import generate_weather_samples


class ParkingMapTests(unittest.TestCase):
    def test_garbage_truck_route_follows_all_waypoints_in_order(self):
        self.assertEqual(GARBAGE_TRUCK_ROUTE[0], (1000, 1425))
        self.assertEqual(GARBAGE_TRUCK_ROUTE[-1], (1000, 1425))
        self.assertEqual([frame[:2] for frame in
                          (garbage_truck_frames[0], garbage_truck_frames[-1])],
                         [(1000, 1425), (1000, 1425)])

        next_frame = 0
        for point in GARBAGE_TRUCK_ROUTE:
            matching = (i for i in range(next_frame, len(garbage_truck_frames))
                        if math.dist(garbage_truck_frames[i][:2], point) <= 15)
            next_frame = next(matching) + 1

    def test_garbage_truck_frames_have_smooth_positions_and_turns(self):
        for first, second in zip(garbage_truck_frames, garbage_truck_frames[1:]):
            self.assertLessEqual(math.dist(first[:2], second[:2]), GARBAGE_TRUCK_STEP + 2)
            turn = (second[2] - first[2] + 180) % 360 - 180
            self.assertLessEqual(abs(turn), 60)

        def near(point):
            return min(garbage_truck_frames,
                       key=lambda frame: math.dist(frame[:2], point))

        self.assertAlmostEqual(near((500, 1425))[2], 90, delta=5)  # влево
        self.assertAlmostEqual(near((336, 600))[2], 0, delta=5)  # вверх
        self.assertAlmostEqual(near((500, 270))[2], -90, delta=5)  # вправо
        self.assertAlmostEqual(abs(near((607, 700))[2]), 180, delta=5)  # вниз

    def test_garbage_truck_draws_at_image_coordinates_without_jitter(self):
        target = (850, 1425)
        index = min(range(len(garbage_truck_frames)),
                    key=lambda i: math.dist(garbage_truck_frames[i][:2], target))
        exit_index = min(range(len(garbage_truck_frames)),
                         key=lambda i: (math.dist(garbage_truck_frames[i][:2], (700, 1425)), -i))
        sprite = Image.new("RGBA", (20, 40), (255, 0, 0, 255))
        with (
            patch("utils.map_generator.get_car", return_value=sprite),
            patch("utils.map_generator._rotate_point", side_effect=AssertionError("legacy transform")),
            patch("utils.map_generator.random.randint", side_effect=AssertionError("jitter")),
        ):
            def render(frame_index):
                overlay = Image.new("RGBA", (941, 1672))
                asyncio.run(add_garbage_truck(frame_index, overlay))
                return overlay

            entering = render(index)
            leaving = render(exit_index)
            outside = render(0)
            repeated = render(index + len(garbage_truck_frames))

        self.assertEqual(entering.getpixel(target), (255, 0, 0, 255))
        self.assertIsNotNone(leaving.getbbox())
        self.assertIsNone(outside.getbbox())
        self.assertEqual(entering.tobytes(), repeated.tobytes())

    def test_garbage_truck_uses_the_same_shadow_direction_as_parked_cars(self):
        overlay = Image.new("RGBA", (941, 1672))
        sprite = Image.new("RGBA", (20, 40), (255, 0, 0, 255))
        with (
            patch("utils.map_generator.get_car", return_value=sprite),
            patch("utils.map_generator.draw_car_with_shadow") as draw_car,
        ):
            for winter, sun, expected in (
                    (0, 0, (7, -7, 10)),
                    (0, 100, (4, -5, 4)),
                    (1, 100, (2, -2, 3)),
            ):
                with self.subTest(winter=winter, sun=sun):
                    asyncio.run(add_garbage_truck(8, overlay, winter, sun))
                    self.assertEqual(tuple(draw_car.call_args.kwargs[key] for key in
                                           ("shadow_dx", "shadow_dy", "blur_radius")), expected)

    def test_temperature_is_large_and_contrasting(self):
        image = Image.new("RGBA", (400, 170), (0, 0, 0, 0))
        _draw_temperature(image, "+12°", "")

        bbox = image.getbbox()
        self.assertIsNotNone(bbox)
        self.assertGreater(bbox[2] - bbox[0], 60)
        self.assertGreater(bbox[3] - bbox[1], 45)
        colors = {color for _, color in image.getcolors(image.width * image.height)}
        self.assertIn((255, 255, 255, 255), colors)
        self.assertIn((24, 28, 32, 255), colors)

    def test_missing_temperature_does_not_draw_a_label(self):
        image = Image.new("RGBA", (400, 170), (0, 0, 0, 0))
        _draw_temperature(image, "", "")
        self.assertIsNone(image.getbbox())

    def test_all_spots_fit_parking_area(self):
        layouts = [get_spot_layout(i) for i in range(1, 75)]
        self.assertTrue(all(layouts))
        for x, y, car_x, car_y, angle in layouts:
            self.assertGreaterEqual(x, 190)
            self.assertLess(x, 800)
            self.assertGreaterEqual(y, 160)
            self.assertLess(y, 1100)

    def test_numbering_runs_from_bottom_left_to_top_right(self):
        first = get_spot_layout(1)
        last = get_spot_layout(74)
        self.assertLess(first[0], last[0])
        self.assertGreater(first[1], last[1])

    def test_numbering_and_alignment_match_reference(self):
        # 1 сверху / 17 снизу; 18 напротив 2; 33 напротив 17.
        self.assertLess(get_spot_layout(1)[1], get_spot_layout(17)[1])
        self.assertEqual(get_spot_layout(18)[1], get_spot_layout(2)[1])
        self.assertEqual(get_spot_layout(33)[1], get_spot_layout(17)[1])
        self.assertEqual(get_spot_layout(35)[1], get_spot_layout(18)[1])
        # 52 совпадает по высоте с местами 6, 22 и 39.
        self.assertEqual(get_spot_layout(52)[1], get_spot_layout(6)[1])
        self.assertEqual(get_spot_layout(52)[1], get_spot_layout(22)[1])
        self.assertEqual(get_spot_layout(52)[1], get_spot_layout(39)[1])

    def test_long_spots_65_to_68(self):
        self.assertEqual(_spot_size(65), (46, 129))
        self.assertEqual(get_spot_layout(65)[0], get_spot_layout(53)[0] + 90)
        self.assertEqual(get_spot_layout(66)[0] - (get_spot_layout(65)[0] + 46), 51)
        self.assertEqual(get_spot_layout(66)[1], get_spot_layout(56)[1])
        self.assertEqual(get_spot_layout(67)[1], get_spot_layout(59)[1])
        self.assertEqual(get_spot_layout(68)[1], get_spot_layout(62)[1])
        self.assertEqual(get_spot_layout(66)[1] + 129, get_spot_layout(67)[1])
        self.assertEqual(get_spot_layout(67)[1] + 129, get_spot_layout(68)[1])

    def test_places_69_to_74_are_adjacent_vertical_bays(self):
        self.assertEqual(_spot_size(74)[1], 85)
        self.assertEqual(get_spot_layout(69)[1], get_spot_layout(74)[1])
        self.assertLess(get_spot_layout(69)[0], get_spot_layout(74)[0])
        for spot_id in range(69, 74):
            self.assertEqual(
                get_spot_layout(spot_id)[0] + _spot_size(spot_id)[0],
                get_spot_layout(spot_id + 1)[0],
            )
        self.assertEqual(get_spot_layout(1)[3], get_spot_layout(1)[1] + 4)

    def test_label_modes_render_same_canvas_and_differ_at_car(self):
        spot = SimpleNamespace(
            id=1, x=0, y=0, width=50, height=100,
            status=SpotStatus.OCCUPIED, current_driver_id=1,
            current_driver=None,
        )
        weather = ("+12°", {"icon": ""}, "test")
        with patch("utils.map_generator._random_car_spots", return_value=[]):
            below = asyncio.run(generate_parking_map(
                [spot], {}, None, weather_override=weather))
            above = asyncio.run(generate_parking_map(
                [spot], {}, None, weather_override=weather,
                labels_above_cars=True))
        self.assertEqual(below.size, (941, 1672))
        self.assertEqual(above.size, below.size)
        self.assertIsNotNone(below.getbbox())
        self.assertNotEqual(below.tobytes(), above.tobytes())

    def test_queue_cars_use_driver_car_and_queue_order(self):
        drivers = [
            SimpleNamespace(id=11, attributes={"car_index": 7}),
            SimpleNamespace(id=12, attributes={}),
            SimpleNamespace(id=13, attributes={"car_index": 19}),
        ]
        entries = [SimpleNamespace(driver=driver) for driver in drivers]

        cars = list(_queue_cars(entries))

        self.assertEqual(len(cars), 3)
        self.assertEqual([car[0] for car in cars], [7, 12 % 60, 19])
        self.assertEqual(cars[0][1:], (QUEUE_SPOT_X + 5, QUEUE_SPOT_Y + 3, 90))
        self.assertEqual(cars[1][1] - cars[0][1], SPOT_HEIGHT)

    def test_queue_cars_are_limited_to_visual_spots(self):
        entries = [
            SimpleNamespace(driver=SimpleNamespace(id=index, attributes={}))
            for index in range(QUEUE_SPOT_COUNT + 3)
        ]

        self.assertEqual(len(list(_queue_cars(entries))), QUEUE_SPOT_COUNT)

    def test_queue_markings_are_rendered_without_labels(self):
        weather = ("+12°", {"icon": ""}, "test")
        with (
            patch("utils.map_generator._random_car_spots", return_value=[]),
            patch("utils.map_generator._draw_queue_spot_markings", wraps=_draw_queue_spot_markings) as markings,
            patch("utils.map_generator._draw_parked_car") as draw_car,
        ):
            images = [
                asyncio.run(generate_parking_map(
                    [], {}, None, weather_override=weather,
                    labels_above_cars=above, queue_entries=[]))
                for above in (False, True)
            ]

        self.assertEqual(markings.call_count, 2)
        draw_car.assert_not_called()
        image = images[0]
        self.assertEqual(image.size, (941, 1672))
        self.assertLess(QUEUE_SPOT_X + QUEUE_SPOT_COUNT * SPOT_HEIGHT, image.width)
        self.assertLess(QUEUE_SPOT_Y + SPOT_WIDTH, image.height)
        self.assertNotEqual(
            image.getpixel((QUEUE_SPOT_X, QUEUE_SPOT_Y + 30)),
            image.getpixel((QUEUE_SPOT_X + 5, QUEUE_SPOT_Y + 30)),
        )
        road = (QUEUE_SPOT_X, QUEUE_SPOT_Y,
                QUEUE_SPOT_X + QUEUE_SPOT_COUNT * SPOT_HEIGHT,
                QUEUE_SPOT_Y + SPOT_WIDTH + 1)
        self.assertEqual(images[0].crop(road).tobytes(), images[1].crop(road).tobytes())
        # Открыто сверху: там нет линии, нижняя граница размечена.
        self.assertNotEqual(
            image.getpixel((QUEUE_SPOT_X + 40, QUEUE_SPOT_Y)),
            image.getpixel((QUEUE_SPOT_X + 40, QUEUE_SPOT_Y + SPOT_WIDTH)),
        )

    def test_render_first_eight_queue_drivers_even_with_offered_spot(self):
        entries = [
            SimpleNamespace(
                driver=SimpleNamespace(id=index + 1, attributes={"car_index": index}),
                spot_id=5 if index == 0 else None,
            )
            for index in range(QUEUE_SPOT_COUNT + 2)
        ]
        weather = ("+12°", {"icon": ""}, "test")
        with (
            patch("utils.map_generator._random_car_spots", return_value=[]),
            patch("utils.map_generator._draw_parked_car") as draw_car,
        ):
            asyncio.run(generate_parking_map(
                [], {}, None, weather_override=weather, queue_entries=entries))

        self.assertEqual(draw_car.call_count, QUEUE_SPOT_COUNT)
        self.assertEqual([call.args[1] for call in draw_car.call_args_list],
                         list(range(QUEUE_SPOT_COUNT)))
        self.assertEqual([call.args[2] for call in draw_car.call_args_list],
                         [QUEUE_SPOT_X + 5 + i * SPOT_HEIGHT
                          for i in range(QUEUE_SPOT_COUNT)])
        self.assertTrue(all(call.args[4] == 90 for call in draw_car.call_args_list))

    def test_map_message_passes_same_queue_snapshot_to_image(self):
        entries = [
            SimpleNamespace(
                driver=SimpleNamespace(id=index + 1, description=f"Водитель {index}"),
                spot_id=None,
            )
            for index in range(QUEUE_SPOT_COUNT + 1)
        ]
        session = SimpleNamespace(refresh=AsyncMock())
        with (
            patch("handlers.map_handlers.ParkingService") as parking_service,
            patch("handlers.map_handlers.QueueService") as queue_service,
            patch("handlers.map_handlers.generate_parking_map", new_callable=AsyncMock) as render,
        ):
            parking_service.return_value.get_spots_with_reservations = AsyncMock(
                return_value=([], {}))
            queue_service.return_value.get_all = AsyncMock(return_value=entries)
            render.return_value = Image.new("RGBA", (10, 10))
            message, _ = asyncio.run(build_map_message(
                session, None, date(2026, 10, 11), False, 0))

        self.assertEqual(render.call_args.kwargs["queue_entries"], entries)
        self.assertEqual(queue_service.return_value.get_all.await_count, 1)
        self.assertIn("9 человек", str(message))
        self.assertIn("Водитель 8", str(message))

    def test_weather_samples_include_three_queue_cars(self):
        with (
            tempfile.TemporaryDirectory() as output_dir,
            patch("services.weather_service.weather_map", {
                "01": {"icon": ""},
                "04": {"icon": ""},
                "10": {"icon": ""},
                "11": {"icon": ""},
            }),
            patch("utils.map_generator.generate_parking_map", new_callable=AsyncMock) as render,
        ):
            render.return_value = Image.new("RGBA", (10, 10))
            asyncio.run(generate_weather_samples(output_dir))

        self.assertGreater(render.await_count, 0)
        for call in render.await_args_list:
            entries = call.kwargs["queue_entries"]
            self.assertEqual(len(entries), 3)
            self.assertEqual([entry.driver.attributes["car_index"] for entry in entries],
                             [5, 18, 42])


if __name__ == "__main__":
    unittest.main()
