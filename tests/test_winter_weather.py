import tempfile
import unittest
from pathlib import Path

from PIL import Image

from services.weather_service import weather_map
from utils.map_generator import (
    FROST_SNOW_MULTIPLIER,
    GARBAGE_TRUCK_ROUTE,
    PARKING_LANES,
    SNOWFALL_MULTIPLIER,
    _winter_keep_out_areas,
    _winter_surface_mask,
)
from utils.weather_generator import (
    SNOW_LAYERS,
    add_snow,
    frost_car,
    get_clouds_layer,
    make_fog_layer,
    make_snow_cover_layer,
    make_sun_glare_layer,
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

    def test_winter_snow_has_more_depth_layers_and_particles(self):
        self.assertEqual(len(SNOW_LAYERS), 5)
        self.assertAlmostEqual(sum(layer[0] for layer in SNOW_LAYERS), 1.0)
        self.assertEqual(SNOWFALL_MULTIPLIER, 7.0)
        self.assertEqual(FROST_SNOW_MULTIPLIER, 1.8)

    def test_top_down_fog_is_patchy_and_deterministic(self):
        first = make_fog_layer((180, 240), seed=42)
        repeated = make_fog_layer((180, 240), seed=42)
        changed = make_fog_layer((180, 240), seed=43)

        self.assertEqual(first.tobytes(), repeated.tobytes())
        self.assertNotEqual(first.tobytes(), changed.tobytes())

        alpha = first.getchannel("A")
        min_alpha, max_alpha = alpha.getextrema()
        self.assertLess(min_alpha, max_alpha)
        row_min, row_max = alpha.crop((0, 100, 180, 101)).getextrema()
        self.assertLess(row_min, row_max)

    def test_sun_glare_keeps_soft_radial_gradient(self):
        glare = make_sun_glare_layer(
            (240, 320),
            center=(60, 240),
            max_alpha=120,
        )
        alpha = glare.getchannel("A")

        self.assertEqual(glare.size, (240, 320))
        self.assertLessEqual(alpha.getextrema()[1], 120)
        self.assertGreater(alpha.getpixel((60, 240)), alpha.getpixel((239, 0)))

    def test_cartoon_clouds_are_deterministic_for_weather(self):
        base = Image.new("RGBA", (240, 320), (0, 0, 0, 0))
        first = get_clouds_layer(base, num_clouds=10, seed=42)
        repeated = get_clouds_layer(base, num_clouds=10, seed=42)
        changed = get_clouds_layer(base, num_clouds=10, seed=43)

        self.assertEqual(first.tobytes(), repeated.tobytes())
        self.assertNotEqual(first.tobytes(), changed.tobytes())

    def test_cartoon_clouds_have_soft_offset_shadows(self):
        base = Image.new("RGBA", (240, 320), (0, 0, 0, 0))
        layer = get_clouds_layer(
            base,
            num_clouds=4,
            cloud_size_range=(60, 90),
            opacity=220,
            blur_radius=3,
            cloud_color=(255, 255, 255),
            shadow_color=(20, 35, 55),
            shadow_offset=(24, 28),
            shadow_opacity=120,
            shadow_blur_radius=5,
            seed=42,
        )

        has_shadow_only_pixel = any(
            layer.getpixel((x, y))[3] > 0
            and layer.getpixel((x, y))[0] < 100
            for y in range(layer.height)
            for x in range(layer.width)
        )
        self.assertTrue(has_shadow_only_pixel)

    def test_weather_types_use_different_cloud_sizes(self):
        self.assertEqual(weather_map["02"]["cloud_size_range"], (150, 250))
        self.assertEqual(weather_map["03"]["cloud_size_range"], (100, 230))
        self.assertEqual(weather_map["04"]["cloud_size_range"], (170, 300))
        self.assertEqual(weather_map["11"]["cloud_size_range"], (190, 340))
        self.assertEqual(weather_map["13"]["cloud_size_range"], (120, 240))

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
