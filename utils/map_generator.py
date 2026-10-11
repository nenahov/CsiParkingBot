import asyncio
import hashlib
import math
import random
from datetime import date

from PIL import Image, ImageDraw, ImageFont, ImageFilter

from models.driver import Driver
from models.parking_spot import ParkingSpot, SpotStatus
from services.weather_service import WeatherService
from utils.cars_generator import get_car, draw_car_with_shadow, cars_count
from utils.weather_generator import make_sun_glare_layer, make_rain_layer, get_clouds_layer, add_snow, \
    LIGHTNING_CHANCE, make_snow_cover_layer, make_winter_tint, frost_car, make_sun_warmth_layer, \
    make_fog_layer

SPOT_HEIGHT = 90
SPOT_WIDTH = 46
SPOT_LABEL_FONT_SIZE = 28

# Визуальные места очереди вдоль нижнего края дороги map3.png (не места из БД).
QUEUE_SPOT_COUNT = 13
QUEUE_SPOT_X = 151
QUEUE_SPOT_Y = 1510

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
GARBAGE_TRUCK_STEP = 20
GARBAGE_TRUCK_TURN_CUT = 24

# Координаты центров машины непосредственно на map3.png; начало и конец — за картой.
GARBAGE_TRUCK_ROUTE = (
    (1000, 1425), (850, 1425), (140, 1425), (75, 1380),
    (85, 1100), (160, 1082), (340, 1060), (336, 833),
    (340, 300), (400, 270), (605, 270), (637, 334),
    (610, 404), (607, 1062), (557, 1103), (137, 1100),
    (80, 1138), (80, 1400), (170, 1420), (700, 1425),
    (1000, 1425),
)


def _interpolate_route(points, step):
    """Прямые с квадратичным скруглением углов; направление берётся из траектории."""
    path = [points[0]]

    def line_to(target):
        start = path[-1]
        count = max(1, math.ceil(math.dist(start, target) / step))
        for index in range(1, count + 1):
            t = index / count
            path.append((start[0] + (target[0] - start[0]) * t,
                         start[1] + (target[1] - start[1]) * t))

    for previous, corner, following in zip(points, points[1:], points[2:]):
        incoming_length = math.dist(previous, corner)
        outgoing_length = math.dist(corner, following)
        if not incoming_length or not outgoing_length:
            line_to(corner)
            continue
        incoming = ((corner[0] - previous[0]) / incoming_length,
                    (corner[1] - previous[1]) / incoming_length)
        outgoing = ((following[0] - corner[0]) / outgoing_length,
                    (following[1] - corner[1]) / outgoing_length)
        # Не добавляем лишних кривых на почти прямой дороге.
        if incoming[0] * outgoing[0] + incoming[1] * outgoing[1] > 0.999:
            line_to(corner)
            continue
        cut = min(GARBAGE_TRUCK_TURN_CUT, incoming_length / 3, outgoing_length / 3)
        approach = (corner[0] - incoming[0] * cut, corner[1] - incoming[1] * cut)
        departure = (corner[0] + outgoing[0] * cut, corner[1] + outgoing[1] * cut)
        line_to(approach)
        count = max(2, math.ceil(2 * cut / step))
        for index in range(1, count + 1):
            t = index / count
            path.append(((1 - t) ** 2 * approach[0] + 2 * (1 - t) * t * corner[0] + t ** 2 * departure[0],
                         (1 - t) ** 2 * approach[1] + 2 * (1 - t) * t * corner[1] + t ** 2 * departure[1]))
    line_to(points[-1])

    frames = []
    for index, (x, y) in enumerate(path):
        before = path[max(0, index - 1)]
        after = path[min(len(path) - 1, index + 1)]
        # Исходный вертикальный спрайт смотрит вверх; Pillow поворачивает против часовой стрелки.
        angle = math.degrees(math.atan2(before[0] - after[0], before[1] - after[1]))
        frames.append((round(x), round(y), angle))
    return frames


garbage_truck_frames = _interpolate_route(GARBAGE_TRUCK_ROUTE, GARBAGE_TRUCK_STEP)

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
d_width = -1


def _rotate_point(x, y):
    # map3: повернутая парковка занимает область примерно x=220..790,
    # y=170..1100. Эти коэффициенты привязывают прежнюю схему к асфальту.
    return round(200 + y * .9), round(170 + (1111 - x) * .85)


def _rotate_box(box):
    x1, y1, x2, y2 = box
    a = _rotate_point(x1, y1)
    b = _rotate_point(x2, y2)
    return min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])


# Зимние колеи идут по фактической траектории движения на map3.png.
# Старые прямоугольные полосы были привязаны к parking_r.png и после замены
# подложки заметно «уезжали» на парковочные места и декоративные объекты.
PARKING_LANES = (GARBAGE_TRUCK_ROUTE,)

# Оставлено для совместимости с внешними импортами. Реальные зоны
# исключения строятся из актуальной раскладки мест в _winter_keep_out_areas().
PARKING_SPOT_AREAS = ()

SNOWFALL_MULTIPLIER = 2.0
FROST_SNOW_MULTIPLIER = 1.3

RANDOM_CARS_EXTRA_MAX = 3
RANDOM_CARS_EXCLUDED = set()


def get_spot_layout(spot_id: int):
    """(x, y, car_x, car_y, car_rotate) по подложке map3.png."""
    if 1 <= spot_id <= 17:
        x, y, angle = 207, 256 + (spot_id - 1) * SPOT_WIDTH, 90
    elif 18 <= spot_id <= 34:
        x, y, angle = 390, 299 + (spot_id - 18) * SPOT_WIDTH, 270
    elif 35 <= spot_id <= 51:
        x, y, angle = 390 + SPOT_HEIGHT, 299 + (spot_id - 35) * SPOT_WIDTH, 90
    elif 52 <= spot_id <= 64:
        x, y, angle = 667, 415 + (spot_id - 52) * SPOT_WIDTH, 270
    elif spot_id == 65:
        # Длинное место примыкает сбоку к обычным местам 53–55.
        return 759, 545, 763, 562, 180
    elif 66 <= spot_id <= 68:
        first_y = 686
        step = 126
        y = round(first_y + (spot_id - 66) * step)
        return 810, y, 815, y + 16, 180
    elif 69 <= spot_id <= 74:
        # Верхний ряд
        first_x = 321
        last_x = 545
        step = (last_x - first_x) / 5
        x = round(first_x + (spot_id - 69) * step)
        # Верхний ряд мест находится над основными рядами парковки.
        y, angle = 160, 180
    else:
        return None
    return x, y, x + 5, y + 4, angle


def _winter_keep_out_areas():
    """Прямоугольники парковочных мест в координатах map3.png.

    Колеи могут проходить рядом с рядами мест, но не должны затемнять
    разметку/номера и рисовать две дополнительные полосы поверх машин.
    Раскладка берётся из get_spot_layout(), поэтому больше не дублирует
    старую геометрию парковки.
    """
    areas = []
    for spot_id in range(1, 75):
        layout = get_spot_layout(spot_id)
        if layout is None:
            continue
        x, y, *_ = layout
        width, height = _spot_size(spot_id)
        padding = 3
        areas.append((
            max(0, x - padding),
            max(0, y - padding),
            min(parking_img.width, x + width + padding),
            min(parking_img.height, y + height + padding),
        ))
    return areas


def _winter_surface_mask():
    """Mask the drivable/parking surface of map3.png.

    The luminance check in weather_generator still follows the painted
    asphalt edges, while this mask prevents similarly dark roofs, trees and
    decorations elsewhere on the new illustrated map from being snowed over.
    """
    mask = Image.new("L", parking_img.size, 0)
    draw = ImageDraw.Draw(mask)

    # Main roads, including the lower queue road and the left access road.
    draw.line(GARBAGE_TRUCK_ROUTE, fill=255, width=138, joint="curve")
    draw.rectangle((0, 1360, parking_img.width, 1635), fill=255)

    # Parking bays are snow-covered too; only the rut layer excludes them.
    for x0, y0, x1, y1 in _winter_keep_out_areas():
        draw.rectangle((x0 - 5, y0 - 5, x1 + 5, y1 + 5), fill=255)

    return mask.filter(ImageFilter.GaussianBlur(3))


def _weather_static_seed(temp, weather, desc):
    """Stable seed for surface snow and frost.

    A new map request must not reshuffle the snow texture or the frost on
    cars. Falling snow gets a separate frame-dependent seed below.
    """
    weather_values = sorted(
        (key, value)
        for key, value in weather.items()
        if not key.startswith("debug_")
    )
    payload = f"{temp}|{desc}|{weather_values}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def _draw_queue_spot_markings(overlay):
    """Восемь смежных мест без номеров, открытых со стороны дороги сверху."""
    draw = ImageDraw.Draw(overlay)
    left = dx + QUEUE_SPOT_X
    top = dy + QUEUE_SPOT_Y
    right = left + QUEUE_SPOT_COUNT * SPOT_WIDTH
    color = (245, 245, 245, 190)
    draw.line((left, top + SPOT_HEIGHT, right, top + SPOT_HEIGHT), fill=color, width=2)
    for index in range(QUEUE_SPOT_COUNT + 1):
        x = left + index * SPOT_WIDTH
        draw.line((x, top, x, top + SPOT_HEIGHT), fill=color, width=2)


def _queue_cars(queue_entries):
    """Координаты и машины первых водителей очереди слева направо."""
    for index, entry in enumerate(queue_entries[:QUEUE_SPOT_COUNT]):
        driver = entry.driver
        car_index = (driver.attributes or {}).get("car_index", driver.id % cars_count)
        x = QUEUE_SPOT_X + index * SPOT_WIDTH
        yield car_index, x + (SPOT_WIDTH - 40) // 2, QUEUE_SPOT_Y + (SPOT_HEIGHT - 80) // 2, 0


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
parking_img = Image.open("./pics/map3.png").convert("RGBA")

try:
    temperature_font = ImageFont.truetype("arialbd.ttf", 68)
except OSError:
    try:
        temperature_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 68)
    except OSError:
        temperature_font = ImageFont.load_default(68)
try:
    emoji_font = ImageFont.truetype("./pics/NotoColorEmoji.ttf", 109)
except Exception as e:
    emoji_font = ImageFont.load_default()
    print("Ошибка загрузки шрифта NotoColorEmoji.ttf", e)


async def generate_parking_map(parking_spots,
                               reservations_data,
                               driver: Driver,
                               use_spot_status: bool = True,
                               frame_index: int = None,
                               day: date = None,
                               is_test: bool = False,
                               weather_override: tuple = None,
                               labels_above_cars: bool = False,
                               queue_entries=None):
    overlay = Image.new("RGBA", parking_img.size, (0, 0, 0, 0))
    if weather_override is not None:
        temp, weather, desc = weather_override
    elif not is_test:
        temp, weather, desc = await WeatherService().get_weather_string(day)
    else:
        temp, weather, desc = await WeatherService().get_weather_test(day)
    sun_alpha = weather.get("sun_alpha", 0)
    winter_strength = _winter_strength(temp, weather)
    static_seed = _weather_static_seed(temp, weather, desc)
    # Солнце рисуем вначале, дождь, снег и туман — в конце
    if sun_alpha > 0:
        sun_layer = make_sun_glare_layer(
            (overlay.width, overlay.height),
            center=(overlay.width * .15, overlay.height * .82),
            max_alpha=sun_alpha,
        )
        overlay = Image.alpha_composite(overlay, sun_layer)
        if winter_strength == 0:
            overlay = Image.alpha_composite(overlay, make_sun_warmth_layer(parking_img))

    if winter_strength > 0:
        overlay = Image.alpha_composite(
            overlay,
            make_snow_cover_layer(
                parking_img,
                winter_strength,
                PARKING_LANES,
                _winter_keep_out_areas(),
                seed=static_seed,
                surface_mask=_winter_surface_mask(),
                debug_dir=(
                        weather.get("debug_winter_masks_dir")
                        or ("pics/temp" if weather.get("debug_winter_masks") else None)
                ),
            ),
        )

    parked_cars = []
    for spot_id in _random_car_spots(parking_spots, use_spot_status):
        _, _, car_x, car_y, car_rotate = get_spot_layout(spot_id)
        parked_cars.append((random.randrange(cars_count), car_x, car_y, car_rotate))

    # Отрисовка всех мест с учетом статусов
    for spot in parking_spots:
        status = get_status(driver, reservations_data, spot, use_spot_status)

        layout = get_spot_layout(spot.id)
        if layout is not None:
            x, y, car_x, car_y, car_rotate = layout
        else:
            x, y, car_x, car_y, car_rotate = spot.x, spot.y, -1000, -1000, 0

        if _shows_driver_car(spot, use_spot_status):
            if spot.current_driver:
                car_index = spot.current_driver.attributes.get("car_index", spot.current_driver_id % cars_count)
            else:
                car_index = spot.current_driver_id % cars_count

            parked_cars.append((car_index, car_x, car_y, car_rotate))
        else:
            # Создаем паттерн с диагональными полосами
            w, h = _spot_size(spot.id) if layout is not None else (spot.width + d_width, spot.height)
            pattern = create_diagonal_pattern(w, h,
                                              stripe_width=4,
                                              color2=COLORS[status],
                                              color1=(0, 0, 0, 0))
            # Вставляем паттерн в прямоугольник
            overlay.paste(pattern, (dx + x, dy + y), pattern)

    if not labels_above_cars:
        _draw_spot_labels(overlay)
    _draw_spot_markings(overlay)
    _draw_queue_spot_markings(overlay)
    parked_cars.extend(_queue_cars(list(queue_entries or ())))
    for car_index, car_x, car_y, car_rotate in parked_cars:
        _draw_parked_car(
            overlay,
            car_index,
            car_x,
            car_y,
            car_rotate,
            winter_strength,
            sun_alpha,
            frost_seed=static_seed + car_index * 1000003 + car_x * 101 + car_y,
        )

    if labels_above_cars:
        _draw_spot_labels(overlay)

    if frame_index is not None:
        await add_garbage_truck(
            frame_index,
            overlay,
            winter_strength,
            sun_alpha,
            frost_seed=static_seed + GARBAGE_TRUCK_CAR_INDEX,
        )

    # Снеговик под облаками, хлопья и дождь — поверх
    rain_drop_count = weather.get("rain_drop_count", 0)
    snow_count = weather.get("snow_count", 0)
    dynamic_seed = (
        None
        if frame_index is None
        else static_seed + frame_index * 1009
    )
    if snow_count > 0:
        overlay = await add_snowman(overlay, seed=static_seed)

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
                           snow_size_range=(2, 3), seed=dynamic_seed)
    if snow_count > 0:
        overlay = add_snow(
            overlay,
            snow_count=int(snow_count * SNOWFALL_MULTIPLIER),
            seed=None if dynamic_seed is None else dynamic_seed + 1,
        )

    # Дождь поверх облаков, иначе облака его закрывают
    if rain_drop_count > 0 and "-" not in temp:
        overlay = make_rain_layer(overlay, drop_count=rain_drop_count,
                                  lightning_chance=weather.get("lightning_chance", LIGHTNING_CHANCE))

    if winter_strength > 0:
        tint_strength = winter_strength * (0.5 if sun_alpha > 0 else 1.0)
        overlay = Image.alpha_composite(overlay, make_winter_tint(overlay.size, tint_strength))

    if is_fog:
        overlay = Image.alpha_composite(overlay, make_fog_layer(overlay.size))

    # Температура и значок остаются читаемыми поверх любых погодных эффектов.
    _draw_temperature(overlay, temp, weather.get("icon", ""))

    result = Image.alpha_composite(parking_img, overlay)

    return result


def _draw_temperature(overlay, temp, icon):
    draw = ImageDraw.Draw(overlay)
    text = str(temp or "").strip()
    icon_x = 125
    if text:
        text_x, text_y = 28, 35
        draw.text(
            (text_x, text_y), text, font=temperature_font,
            fill=(255, 255, 255, 255),
            stroke_width=3, stroke_fill=(24, 28, 32, 255),
        )
        bbox = draw.textbbox((text_x, text_y), text, font=temperature_font, stroke_width=3)
        icon_x = max(icon_x, bbox[2] + 16)
    if icon:
        draw.text((icon_x, 25), text=icon, font=emoji_font, embedded_color=True)


def _draw_spot_markings(overlay):
    """Рисует светлую разметку всех 74 мест."""
    draw = ImageDraw.Draw(overlay)
    for spot_id in range(1, 75):
        layout = get_spot_layout(spot_id)
        if layout is None:
            continue
        x, y, car_x, car_y, car_rotate = layout
        w, h = _spot_size(spot_id)
        _draw_spot_edges(draw, spot_id, x, y, w, h)


def _draw_spot_labels(overlay):
    draw = ImageDraw.Draw(overlay)
    for font_name in ("arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            font = ImageFont.truetype(font_name, SPOT_LABEL_FONT_SIZE)
            break
        except OSError:
            font = ImageFont.load_default(SPOT_LABEL_FONT_SIZE)

    for spot_id in range(1, 75):
        layout = get_spot_layout(spot_id)
        if layout is None:
            continue
        x, y, *_ = layout
        w, h = _spot_size(spot_id)
        text = str(spot_id)
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        text_x = x + (w - text_width) / 2
        text_y = y + (h - text_height) / 2 - 1

        # Контрастная обводка сохраняет читаемость номера и на машине, и на фоне.
        for offset_x, offset_y in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            draw.text(
                (text_x + offset_x, text_y + offset_y),
                text,
                font=font,
                fill=(24, 28, 32, 255),
            )
        draw.text((text_x, text_y), text, font=font, fill=(255, 255, 255, 255))


def _spot_size(spot_id):
    if spot_id == 65:
        return SPOT_WIDTH, 129
    if 66 <= spot_id <= 68:
        return SPOT_WIDTH, 129
    if 69 <= spot_id < 74:
        return get_spot_layout(spot_id + 1)[0] - get_spot_layout(spot_id)[0], 83
    return (SPOT_WIDTH, 83) if spot_id == 74 else (SPOT_HEIGHT, SPOT_WIDTH)


def _spot_opening(spot_id):
    """Сторона, с которой машина заезжает в карман."""
    if spot_id == 65:
        return "bottom"
    if 1 <= spot_id <= 17 or 35 <= spot_id <= 51:
        return "right"
    if 18 <= spot_id <= 34 or 52 <= spot_id <= 68:
        return "left"
    return "bottom"


def _draw_spot_edges(draw, spot_id, x, y, w, h):
    """Рисует грани серии смежных мест один раз, без щелей и двойных швов."""
    color = (245, 245, 245, 190)
    width = 2
    if 65 <= spot_id <= 68:
        draw.line((x, y, x + w, y), fill=color, width=width)
        # draw.line((x, y, x, y + h), fill=color, width=width)
        draw.line((x + w, y, x + w, y + h), fill=color, width=width)
        if spot_id == 68:
            draw.line((x + w, y + h, x, y + h), fill=color, width=width)
        return

    if 69 <= spot_id <= 74:
        index = spot_id - 69
        # Верхний ряд открыт снизу; внутренние грани рисуются по одному разу.
        if index == 0:
            draw.line((x, y + h, x, y), fill=color, width=width)
        draw.line((x + w, y, x + w, y + h), fill=color, width=width)
        draw.line((x, y, x + w, y), fill=color, width=width)
        return

    # Вертикальные места объединены в колонны: горизонтальную общую грань
    # каждого соседнего места рисуем только со стороны нижнего места.
    if _spot_opening(spot_id) != "left":
        draw.line((x, y + h, x, y), fill=color, width=width)
    if _spot_opening(spot_id) != "right":
        draw.line((x + w, y, x + w, y + h), fill=color, width=width)
    draw.line((x, y, x + w, y), fill=color, width=width)
    if spot_id in (17, 34, 51, 64):
        draw.line((x + w, y + h, x, y + h), fill=color, width=width)


def _draw_parked_car(
        overlay,
        car_index,
        car_x,
        car_y,
        car_rotate,
        winter_strength,
        sun_alpha,
        frost_seed=None,
):
    car_image = get_car(car_index)

    scale = 0.8
    if scale != 1:
        new_size = (int(car_image.width * scale), int(car_image.height * scale))
        car_image = car_image.resize(new_size)
    car_image = car_image.rotate(car_rotate, expand=True)
    if winter_strength > 0:
        car_image = frost_car(car_image, winter_strength, seed=frost_seed)
    shadow_dx, shadow_dy, shadow_blur = _car_shadow_settings(winter_strength, sun_alpha)
    draw_car_with_shadow(
        car_image,
        overlay,
        dx + car_x,
        dy + car_y,
        shadow_dx=shadow_dx,
        shadow_dy=shadow_dy,
        blur_radius=shadow_blur,
    )


def _car_shadow_settings(winter_strength, sun_alpha):
    if sun_alpha > 0:
        # Короткий сдвиг: длинная тень выглядит так, будто машина висит над землёй.
        return (2, -2, 3) if winter_strength > 0 else (4, -5, 4)
    return 7, -7, 10


async def add_snowman(overlay, seed=None):
    # Рисуем снеговика
    index = random.Random(seed).randint(0, 5)
    box = SNOWMAN_BOXES[index]
    snowman = snowman_img.crop(box)
    scale = 0.8
    if scale != 1:
        new_size = (int(snowman.width * scale), int(snowman.height * scale))
        snowman = snowman.resize(new_size)

    snow_w, snow_h = snowman.size

    target_center_x, target_bottom_y = (130, 830)

    paste_x = int(target_center_x - snow_w / 2)
    paste_y = int(target_bottom_y - snow_h)

    # Вставляем с учётом альфа‑канала (третий аргумент — маска)
    overlay.paste(snowman, (paste_x, paste_y), snowman)

    return overlay


async def add_garbage_truck(
        frame_index,
        overlay,
        winter_strength=0,
        sun_alpha=0,
        frost_seed=None,
):
    garbage_truck = get_car(GARBAGE_TRUCK_CAR_INDEX)
    frame = garbage_truck_frames[frame_index % len(garbage_truck_frames)]
    garbage_truck = garbage_truck.rotate(frame[2], expand=True)
    if winter_strength > 0:
        garbage_truck = frost_car(garbage_truck, winter_strength, seed=frost_seed)
    pos = (round(dx + frame[0] - garbage_truck.width / 2),
           round(dy + frame[1] - garbage_truck.height / 2))
    shadow_dx, shadow_dy, shadow_blur = _car_shadow_settings(winter_strength, sun_alpha)
    draw_car_with_shadow(
        garbage_truck, overlay, *pos,
        shadow_dx=shadow_dx, shadow_dy=shadow_dy, blur_radius=shadow_blur,
    )


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
