import asyncio
import random
from datetime import date

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

from models.driver import Driver
from models.parking_spot import ParkingSpot, SpotStatus
from services.weather_service import WeatherService
from utils.build_parking_backdrop import draw_numbers_on_top, ensure_parking_backdrop
from utils.cars_generator import get_car, draw_car_with_shadow, cars_count
from utils.parking_layout import (
    CAR_SCALE,
    GARBAGE_TRUCK_APPROACH,
    GARBAGE_TRUCK_DEPARTURE,
    GARBAGE_TRUCK_PAUSE,
    PARKING_LANES,
    PARKING_SPOT_AREAS,
    QUEUE_SLOTS,
    SNOWMAN_CENTER,
    SPOT_STALLS,
)
from utils.weather_generator import make_sun_glare_layer, make_rain_layer, get_clouds_layer, add_snow, \
    LIGHTNING_CHANCE, make_snow_cover_layer, make_winter_tint, frost_car, make_sun_warmth_layer, \
    make_fog_layer

# Цвета для разных статусов
COLORS = {
    'free_r': (100, 255, 100, 150),  # Светло-зеленый
    'my_reserved': (255, 250, 0, 150),  # Желтый
    'reserved': (255, 20, 20, 97),  # Красный

    str(SpotStatus.HIDDEN): (0, 0, 0, 30),  # Светло-зеленый
    str(SpotStatus.FREE): (100, 255, 100, 200),  # Светло-зеленый
    str(SpotStatus.OCCUPIED): (255, 20, 20, 20),  # Красный
    str(SpotStatus.OCCUPIED_WITHOUT_DEMAND): (255, 20, 20, 250),  # Красный

    str(SpotStatus.HIDDEN) + "_me": (0, 0, 0, 250),  # Светло-зеленый
    str(SpotStatus.FREE) + "_me": (100, 255, 100, 250),  # Светло-зеленый
    str(SpotStatus.OCCUPIED) + "_me": (255, 250, 0, 25),  # Желтый
    str(SpotStatus.OCCUPIED_WITHOUT_DEMAND) + "_me": (255, 200, 20, 250),  # Красный

    'text': (0, 0, 0)  # Черный
}

GARBAGE_TRUCK_CAR_INDEX = 32
GARBAGE_TRUCK_STEP = 55
GARBAGE_TRUCK_SCALE = 0.55


def _interpolate_route(points, step):
    frames = [points[0]]
    for (x1, y1, a1), (x2, y2, a2) in zip(points, points[1:]):
        count = max(1, round(((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5 / step))
        da = (a2 - a1 + 180) % 360 - 180
        for i in range(1, count + 1):
            t = i / count
            frames.append((round(x1 + (x2 - x1) * t), round(y1 + (y2 - y1) * t), round(a1 + da * t)))
    return frames


garbage_truck_frames = ([(-1000, -1000, 0)] * 3
                        + _interpolate_route(GARBAGE_TRUCK_APPROACH, GARBAGE_TRUCK_STEP)
                        + GARBAGE_TRUCK_PAUSE
                        + _interpolate_route(GARBAGE_TRUCK_DEPARTURE, GARBAGE_TRUCK_STEP)[1:])

SNOWMAN_BOXES = [
    (20, 30, 128, 163),
    (133, 30, 233, 163),
    (236, 30, 346, 163),
    (15, 180, 117, 328),
    (129, 180, 241, 327),
    (241, 180, 337, 325),
]

dx = 0
dy = 0

_CAR_W = int(50 * CAR_SCALE)
_CAR_H = int(100 * CAR_SCALE)

SNOWFALL_MULTIPLIER = 2.0
FROST_SNOW_MULTIPLIER = 1.3

RANDOM_CARS_EXTRA_MAX = 3
RANDOM_CARS_EXCLUDED = set(range(65, 69))


def _car_anchor(x, y, w, h, rotate):
    """Левый верх уже повёрнутой машинки внутри клетки."""
    if rotate % 180 == 0:
        return x + (w - _CAR_W) // 2, y + max(0, h - _CAR_H - 1)
    return x + max(0, w - _CAR_H) // 2, y + (h - _CAR_W) // 2


def get_spot_layout(spot_id: int):
    """(x, y, w, h, car_x, car_y, car_rotate) по подложке parking_r.png или None."""
    stall = SPOT_STALLS.get(spot_id)
    if stall is None:
        return None
    x, y, w, h, rotate = stall
    car_x, car_y = _car_anchor(x, y, w, h, rotate)
    return x, y, w, h, car_x, car_y, rotate


def _shows_driver_car(spot, use_spot_status):
    return (use_spot_status
            and spot.current_driver_id is not None
            and spot.status in (SpotStatus.OCCUPIED, SpotStatus.OCCUPIED_WITHOUT_DEMAND))


def _random_car_spots(parking_spots, use_spot_status):
    shown = sum(1 for spot in parking_spots
                if _shows_driver_car(spot, use_spot_status) and get_spot_layout(spot.id) is not None)
    db_ids = {spot.id for spot in parking_spots}
    free = [spot_id for spot_id in range(1, 75)
            if spot_id not in db_ids
            and spot_id not in RANDOM_CARS_EXCLUDED
            and get_spot_layout(spot_id) is not None]
    count = min(shown + random.randint(0, RANDOM_CARS_EXTRA_MAX), len(free))
    return random.sample(free, count)


def _parse_temp(temp):
    if not temp:
        return None
    sign = -1 if "-" in str(temp) else 1
    digits = "".join(ch for ch in str(temp) if ch.isdigit())
    if not digits:
        return None
    return sign * int(digits)


def _winter_strength(temp, weather):
    snow_count = weather.get("snow_count", 0)
    rain_drop_count = weather.get("rain_drop_count", 0)
    if snow_count > 0:
        return 1.0
    temp_value = _parse_temp(temp)
    if temp_value is not None and temp_value < 0 and rain_drop_count > 0:
        return 0.8
    if temp_value is not None and temp_value < 0:
        return 0.6
    return 0

snowman_img = Image.open("./pics/snowman.png").convert("RGBA")

try:
    emoji_font = ImageFont.truetype("./pics/NotoColorEmoji.ttf", 109)
except Exception as e:
    emoji_font = ImageFont.load_default()
    print("Ошибка загрузки шрифта NotoColorEmoji.ttf", e)


def _load_font(size, bold=False):
    names = ("arialbd.ttf", "arial.ttf") if bold else ("arial.ttf",)
    for name in names:
        try:
            return ImageFont.truetype(f"C:/Windows/Fonts/{name}", size)
        except OSError:
            continue
    return ImageFont.load_default()


temp_font = _load_font(26, bold=True)


async def generate_parking_map(parking_spots,
                               reservations_data,
                               driver: Driver,
                               use_spot_status: bool = True,
                               frame_index: int = None,
                               day: date = None,
                               is_test: bool = False,
                               weather_override: tuple = None,
                               queue=None,
                               numbers_on_top: bool = False):
    if weather_override is not None:
        temp, weather, desc = weather_override
    elif not is_test:
        temp, weather, desc = await WeatherService().get_weather_string(day)
    else:
        temp, weather, desc = await WeatherService().get_weather_test(day)
    base = ensure_parking_backdrop(day, temp, weather)
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    sun_alpha = weather.get("sun_alpha", 0)
    winter_strength = _winter_strength(temp, weather)
    # Солнце рисуем вначале, дождь, снег и туман — в конце
    if sun_alpha > 0:
        sun_layer = make_sun_glare_layer((overlay.width, overlay.height), max_alpha=sun_alpha)
        overlay = Image.alpha_composite(overlay, sun_layer)
        if winter_strength == 0:
            overlay = Image.alpha_composite(overlay, make_sun_warmth_layer(base))

    if winter_strength > 0:
        overlay = Image.alpha_composite(
            overlay, make_snow_cover_layer(base, winter_strength, PARKING_LANES, PARKING_SPOT_AREAS))

    for spot_id in _random_car_spots(parking_spots, use_spot_status):
        _x, _y, _w, _h, car_x, car_y, car_rotate = get_spot_layout(spot_id)
        _draw_parked_car(overlay, random.randrange(cars_count), car_x, car_y, car_rotate,
                         winter_strength, sun_alpha)

    # Отрисовка всех мест с учетом статусов
    for spot in parking_spots:
        status = get_status(driver, reservations_data, spot, use_spot_status)

        layout = get_spot_layout(spot.id)
        if layout is not None:
            x, y, w, h, car_x, car_y, car_rotate = layout
        else:
            x, y, w, h = spot.x, spot.y, spot.width, spot.height
            car_x, car_y, car_rotate = -1000, -1000, 0

        if _shows_driver_car(spot, use_spot_status):
            if spot.current_driver:
                car_index = _driver_car_index(spot.current_driver)
            else:
                car_index = spot.current_driver_id % cars_count

            _draw_parked_car(overlay, car_index, car_x, car_y, car_rotate, winter_strength, sun_alpha)
        else:
            pattern = create_diagonal_pattern(w, h,
                                              stripe_width=4,
                                              color2=COLORS[status],
                                              color1=(0, 0, 0, 0))
            overlay.paste(pattern, (dx + x, dy + y), pattern)

    _draw_queue(overlay, queue, winter_strength, sun_alpha)

    if frame_index:
        await add_garbage_truck(frame_index, overlay, winter_strength)

    # Снеговик под облаками, хлопья и дождь — поверх
    rain_drop_count = weather.get("rain_drop_count", 0)
    snow_count = weather.get("snow_count", 0)
    if snow_count > 0:
        overlay = await add_snowman(overlay)

    is_fog = bool(
        weather.get("fog")
        or (
                weather.get("num_clouds", 0) >= 40
                and rain_drop_count == 0
                and snow_count == 0
        )
    )
    if weather.get("num_clouds", 0) > 0 and not is_fog:
        cloud_layer = get_clouds_layer(overlay, num_clouds=weather.get("num_clouds", 0))
        overlay = Image.alpha_composite(overlay, cloud_layer)

    if rain_drop_count > 0 and "-" in temp:
        overlay = add_snow(overlay, snow_count=int(rain_drop_count * FROST_SNOW_MULTIPLIER),
                           snow_size_range=(2, 3))
    if snow_count > 0:
        overlay = add_snow(overlay, snow_count=int(snow_count * SNOWFALL_MULTIPLIER))

    # Дождь поверх облаков, иначе облака его закрывают
    if rain_drop_count > 0 and "-" not in temp:
        overlay = make_rain_layer(overlay, drop_count=rain_drop_count,
                                  lightning_chance=weather.get("lightning_chance", LIGHTNING_CHANCE))

    if winter_strength > 0:
        tint_strength = winter_strength * (0.5 if sun_alpha > 0 else 1.0)
        overlay = Image.alpha_composite(overlay, make_winter_tint(overlay.size, tint_strength))

    if is_fog:
        overlay = Image.alpha_composite(overlay, make_fog_layer(overlay.size))

    # Добавляем текст
    draw = ImageDraw.Draw(overlay)
    draw.text((16, 40), text=temp, font=temp_font, fill=COLORS['text'])
    draw.text((468, -8), text=weather.get("icon", ''), font=emoji_font, embedded_color=True)

    result = Image.alpha_composite(base, overlay)
    if numbers_on_top:
        draw_numbers_on_top(result)
    return result


def _driver_car_index(driver):
    attrs = getattr(driver, "attributes", None) or {}
    fallback = getattr(driver, "id", 0) or 0
    return attrs.get("car_index", fallback % cars_count)


def _draw_queue(overlay, queue, winter_strength, sun_alpha):
    if not queue:
        return
    for (x, y, w, h, car_rotate), entry in zip(QUEUE_SLOTS, queue):
        driver = getattr(entry, "driver", None)
        if driver is None:
            continue
        car_x, car_y = _car_anchor(x, y, w, h, car_rotate)
        _draw_parked_car(overlay, _driver_car_index(driver), car_x, car_y, car_rotate,
                         winter_strength, sun_alpha)


def _draw_parked_car(overlay, car_index, car_x, car_y, car_rotate, winter_strength, sun_alpha):
    car_image = get_car(car_index)
    if winter_strength > 0:
        car_image = frost_car(car_image, winter_strength)

    scale = CAR_SCALE
    if scale != 1:
        new_size = (int(car_image.width * scale), int(car_image.height * scale))
        car_image = car_image.resize(new_size)
    car_image = car_image.rotate(car_rotate, expand=True)
    if sun_alpha > 0:
        # Короткий сдвиг: длинная тень выглядит так, будто машина висит над землёй
        shadow_dx, shadow_dy = ((2, 2) if winter_strength > 0 else (3, 2))
        shadow_blur = 3 if winter_strength > 0 else 4
    else:
        shadow_dx, shadow_dy, shadow_blur = 5, 5, 10
    draw_car_with_shadow(
        car_image,
        overlay,
        dx + car_x,
        dy + car_y,
        shadow_dx=shadow_dx,
        shadow_dy=shadow_dy,
        blur_radius=shadow_blur,
    )


async def add_snowman(overlay):
    # Рисуем снеговика
    index = random.randint(0, 5)
    box = SNOWMAN_BOXES[index]
    snowman = snowman_img.crop(box)
    scale = 0.8
    if scale != 1:
        new_size = (int(snowman.width * scale), int(snowman.height * scale))
        snowman = snowman.resize(new_size)

    snow_w, snow_h = snowman.size

    target_center_x, target_bottom_y = SNOWMAN_CENTER

    paste_x = int(target_center_x - snow_w / 2)
    paste_y = int(target_bottom_y - snow_h)

    # Вставляем с учётом альфа‑канала (третий аргумент — маска)
    overlay.paste(snowman, (paste_x, paste_y), snowman)

    return overlay


async def add_garbage_truck(frame_index, overlay, winter_strength=0):
    garbage_truck = get_car(GARBAGE_TRUCK_CAR_INDEX)
    if winter_strength > 0:
        garbage_truck = frost_car(garbage_truck, winter_strength)
    frame = garbage_truck_frames[frame_index % len(garbage_truck_frames)]
    new_size = (int(garbage_truck.width * GARBAGE_TRUCK_SCALE), int(garbage_truck.height * GARBAGE_TRUCK_SCALE))
    garbage_truck = garbage_truck.resize(new_size)
    garbage_truck = garbage_truck.rotate(frame[2], expand=True)
    pos = (dx + frame[0] + random.randint(-5, 5), dy + frame[1] + random.randint(0, 5))
    # Создаем тень
    shadow = Image.new("RGBA", garbage_truck.size, (0, 0, 0, 0))
    shadow.putalpha(garbage_truck.split()[3])
    shadow = ImageOps.colorize(shadow.convert("L"), black="black", white="black")
    shadow.putalpha(garbage_truck.split()[3])
    blur_radius = 10  # радиус размытия тени
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur_radius))
    # Смещаем тень относительно машины
    shadow_position = (pos[0] + 8, pos[1] + 8)
    # Накладываем тень
    overlay.paste(shadow, shadow_position, mask=garbage_truck)
    overlay.paste(garbage_truck, pos, mask=garbage_truck)


def get_status(driver: Driver, reservations_data, spot: ParkingSpot, use_spot_status: bool):
    if use_spot_status and spot.status is not None:
        return str(spot.status) + ("_me" if driver is not None and spot.current_driver_id == driver.id else "")

    # Проверка резерваций для текущего места
    me = any(res.driver == driver for res in reservations_data.get(spot.id, []))
    other = any(res.driver != driver for res in reservations_data.get(spot.id, []))
    if other and not me:
        return 'reserved'
    elif me:
        return 'my_reserved'
    else:
        return 'free_r'


def create_diagonal_pattern(width, height, stripe_width=10, color1="red", color2="yellow"):
    """Создает изображение с диагональными полосами"""
    # Создаем временное изображение для паттерна
    pattern_size = max(width, height) * 2
    pattern = Image.new("RGBA", (pattern_size, pattern_size), color1)
    draw = ImageDraw.Draw(pattern)

    # Рисуем диагональные полосы
    for i in range(-pattern_size, pattern_size, stripe_width * 2):
        draw.line([(i, 0), (i + pattern_size, pattern_size)],
                  fill=color2, width=stripe_width)

    # Обрезаем до нужного размера
    return pattern.crop((width / 2, height / 2, width + width / 2, height + height / 2))


async def main() -> None:
    img = await generate_parking_map([], None, None, frame_index=12, is_test=True)
    img.save("c:\\\\Temp\\temp.png")


if __name__ == "__main__":
    asyncio.run(main())
