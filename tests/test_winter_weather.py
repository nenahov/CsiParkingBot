import tempfile
import unittest
from pathlib import Path

from PIL import Image

from utils.map_generator import (
    GARBAGE_TRUCK_ROUTE,
    PARKING_LANES,
    _winter_keep_out_areas,
    _winter_surface_mask,
)
from utils.weather_generator import (
    add_snow,
    frost_car,
    make_snow_cover_layer,
    make_winter_tint,
)


class WinterWeatherTests(unittest.TestCase):
    def test_winter_geometry_uses_current_map_route(self):
        self.assertEqual(PARKING_LANES, (GARBAGE_TRUCK_ROUTE,))

        surface = _winter_surface_mask()
        self.assertEqual(surface.size, (941, 1672))
        self.assertEqual(surface.getpixel((1000 % surface.width, 1425)), 255)
        self.assertGreater(surface.getpixel((340, 600)), 0)
        self.assertEqual(surface.getpixel((20, 20)), 0)

        keep_out = _winter_keep_out_areas()
        self.assertEqual(len(keep_out), 74)

    def test_static_winter_layers_are_deterministic(self):
        base = Image.new("RGBA", (120, 180), (45, 50, 55, 255))
        lanes = (((10, 20), (60, 90), (100, 160)),)

        first = make_snow_cover_layer(base, lanes=lanes, seed=123)
        repeated = make_snow_cover_layer(base, lanes=lanes, seed=123)
        changed = make_snow_cover_layer(base, lanes=lanes, seed=124)
        self.assertEqual(first.tobytes(), repeated.tobytes())
        self.assertNotEqual(first.tobytes(), changed.tobytes())

        car = Image.new("RGBA", (40, 80), (200, 20, 20, 255))
        first_frost = frost_car(car, 1, seed=55)
        repeated_frost = frost_car(car, 1, seed=55)
        changed_frost = frost_car(car, 1, seed=56)
        self.assertEqual(first_frost.tobytes(), repeated_frost.tobytes())
        self.assertNotEqual(first_frost.tobytes(), changed_frost.tobytes())

    def test_falling_snow_is_reproducible_per_frame_seed(self):
        base = Image.new("RGBA", (180, 240), (40, 45, 50, 255))
        first = add_snow(base, snow_count=120, seed=7)
        repeated = add_snow(base, snow_count=120, seed=7)
        next_frame = add_snow(base, snow_count=120, seed=8)

        self.assertEqual(first.tobytes(), repeated.tobytes())
        self.assertNotEqual(first.tobytes(), next_frame.tobytes())

    def test_debug_masks_are_written(self):
        base = Image.new("RGBA", (100, 100), (40, 45, 50, 255))
        surface = Image.new("L", base.size, 0)
        surface.paste(255, (10, 10, 90, 90))

        with tempfile.TemporaryDirectory() as output_dir:
            make_snow_cover_layer(
                base,
                lanes=(((10, 50), (90, 50)),),
                keep_out=((40, 40, 60, 60),),
                surface_mask=surface,
                seed=1,
                debug_dir=output_dir,
            )
            files = {path.name for path in Path(output_dir).glob("winter_*.png")}

        self.assertEqual(files, {
            "winter_surface_mask.png",
            "winter_asphalt_mask.png",
            "winter_cover_mask.png",
            "winter_edge_mask.png",
            "winter_keep_out_mask.png",
            "winter_rut_mask.png",
        })

    def test_winter_tint_is_subtle(self):
        self.assertEqual(make_winter_tint((1, 1), 1).getpixel((0, 0))[3], 12)


if __name__ == "__main__":
    unittest.main()
