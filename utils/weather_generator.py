import math
import random
from typing import Union

from PIL import Image, ImageChops
from PIL import ImageDraw, ImageFilter


def make_sun_glare_layer(size, center=None, max_alpha=120, radius=None):
    """
    Создаёт слой «солнечного» градиента на весь кадр.
    """
    w, h = size
    if center is None:
        center = (w * 0.3, h * 0.2)  # сверху слева
    if radius is None:
        radius = int(max(w, h) * 1.05)
    layer = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    # концентрические круги
    for r in range(radius, 0, -1):
        alpha = int(max_alpha * (1 - r / radius))
        color = (255, 255, 200, alpha)
        bbox = [
            (center[0] - r, center[1] - r),
            (center[0] + r, center[1] + r),
        ]
        draw.ellipse(bbox, fill=color)
    return layer.filter(ImageFilter.GaussianBlur(radius * 0.02))


def add_edge_fade_mask(layer, sunny_segs, seg_count=3):
    """
    Возвращает маску освещённости:
    - Солнечные сегменты: полностью α=255.
    - Несолнечные: затухание с той стороны, где есть соседний солнечный сегмент.
    """
    w, h = (layer.width, layer.height)
    seg_w = w // seg_count
    mask = Image.new('L', (w, h), 0)
    pixels = mask.load()

    for seg in range(seg_count):
        x_start = seg * seg_w
        x_end = x_start + seg_w

        if seg in sunny_segs:
            # Солнечный сегмент — полностью залить
            for x in range(x_start, x_end):
                for y in range(h):
                    pixels[x, y] = 255
        else:
            # Не солнечный — определяем соседей
            left_sunny = (seg - 1) in sunny_segs
            right_sunny = (seg + 1) in sunny_segs
            for x in range(x_start, x_end):
                rel_x = x - x_start
                alpha = 0

                if left_sunny and rel_x < seg_w // 2:
                    # Затухание от левого солнечного сегмента
                    alpha = int(255 * (1 - rel_x / (seg_w / 2)))

                elif right_sunny and rel_x >= seg_w // 2:
                    # Затухание от правого солнечного сегмента
                    dx = seg_w - rel_x
                    alpha = int(255 * (1 - dx / (seg_w / 2)))

                for y in range(h):
                    pixels[x, y] = max(pixels[x, y], alpha)

    orig_alpha = layer.getchannel('A')
    combined_alpha = ImageChops.multiply(orig_alpha, mask)
    layer.putalpha(combined_alpha)
    return layer


RAIN_COLOR = (215, 230, 245)
# Тёмная кромка нужна, чтобы светлая капля читалась на белом фоне и облаках
RAIN_EDGE_COLOR = (60, 80, 105)

# (доля капель, длина, ширина, альфа, blur) — от дальнего слоя к ближнему
RAIN_DEPTH_LAYERS = [
    (0.45, (10, 18), 1, (110, 150), 0),
    (0.35, (18, 30), 1, (150, 200), 0),
    (0.20, (30, 50), 2, (180, 230), 0.6),
]


def _draw_rain_streaks(size, count, length_range, width, alpha_range, wind, blur):
    """Слой штрихов дождя: тёмная кромка + светлая сердцевина, хвост прозрачнее головы."""
    layer = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    w, h = size
    parts = 3
    for _ in range(count):
        x = random.uniform(0, w)
        y = random.uniform(-length_range[1], h)
        length = random.uniform(*length_range)
        slope = wind + random.uniform(-0.03, 0.03)
        dx = -length * slope
        dy = length
        alpha = random.randint(*alpha_range)
        shade = random.randint(-15, 15)
        core = tuple(min(255, max(0, c + shade)) for c in RAIN_COLOR)
        for i in range(parts):
            t0 = i / parts
            t1 = (i + 1) / parts
            fade = 0.5 + 0.5 * t1
            x0, y0 = x + dx * t0, y + dy * t0
            x1, y1 = x + dx * t1, y + dy * t1
            draw.line((x0 + 1, y0, x1 + 1, y1),
                      fill=(*RAIN_EDGE_COLOR, int(alpha * fade * 0.6)), width=width)
            draw.line((x0, y0, x1, y1),
                      fill=(*core, int(alpha * fade)), width=width)
    if blur > 0:
        layer = layer.filter(ImageFilter.GaussianBlur(blur))
    return layer


def _draw_splashes(size, count):
    """Брызги от капель, разбивающихся о землю."""
    layer = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    w, h = size
    for _ in range(count):
        x = random.uniform(0, w)
        y = random.uniform(0, h)
        rx = random.uniform(2, 4)
        ry = random.uniform(0.5, 1.5)
        alpha = random.randint(120, 170)
        draw.ellipse((x - rx, y - ry + 1, x + rx, y + ry + 1),
                     outline=(*RAIN_EDGE_COLOR, int(alpha * 0.6)), width=1)
        draw.ellipse((x - rx, y - ry, x + rx, y + ry),
                     outline=(*RAIN_COLOR, alpha), width=1)
    return layer.filter(ImageFilter.GaussianBlur(0.5))


LIGHTNING_CHANCE = 0.21

# (цвет, множитель ширины, альфа, blur) — от внешнего ореола к ядру
LIGHTNING_PASSES = [
    ((140, 150, 255), 7, 70, 14),
    ((190, 210, 255), 3, 150, 4),
    ((255, 255, 255), 1, 255, 0.5),
]


def _lightning_path(p0, p1, displace, detail):
    """Зигзаг методом midpoint displacement: середина смещается перпендикулярно отрезку."""
    (x0, y0), (x1, y1) = p0, p1
    dist = math.hypot(x1 - x0, y1 - y0)
    if dist < detail or displace < 1:
        return [p0, p1]
    nx, ny = -(y1 - y0) / dist, (x1 - x0) / dist
    offset = random.uniform(-displace, displace)
    mid = ((x0 + x1) / 2 + nx * offset, (y0 + y1) / 2 + ny * offset)
    left = _lightning_path(p0, mid, displace / 2, detail)
    right = _lightning_path(mid, p1, displace / 2, detail)
    return left[:-1] + right


def _lightning_branch(points, start_share, end_share, direction, length,
                      angle_range, displace_share):
    """Ветка от случайной точки пути, отклонённая в сторону от направления direction."""
    i = random.randint(int(len(points) * start_share), max(1, int(len(points) * end_share)) - 1)
    ox, oy = points[i]
    angle = direction + random.choice((-1, 1)) * math.radians(random.uniform(*angle_range))
    end = (ox + math.cos(angle) * length, oy + math.sin(angle) * length)
    return _lightning_path((ox, oy), end, length * displace_share, 6), angle


def _lightning_bolts(size):
    """Ствол и ветки молнии: список (точки, коэффициент толщины/яркости)."""
    w, h = size
    start = (random.uniform(w * 0.2, w * 0.8), 0)
    end = (start[0] + random.uniform(-0.25, 0.25) * w, random.uniform(0.65, 0.95) * h)
    trunk_len = math.hypot(end[0] - start[0], end[1] - start[1])
    trunk = _lightning_path(start, end, trunk_len * 0.18, 6)
    direction = math.atan2(end[1] - start[1], end[0] - start[0])

    bolts = [(trunk, 1.0)]
    for _ in range(random.randint(4, 7)):
        branch_len = trunk_len * random.uniform(0.15, 0.4)
        branch, angle = _lightning_branch(trunk, 0.05, 0.66, direction, branch_len, (25, 60), 0.15)
        bolts.append((branch, 0.55))
        if random.random() < 0.4 and len(branch) > 4:
            sub, _ = _lightning_branch(branch, 0.2, 0.7, angle, branch_len * random.uniform(0.4, 0.6),
                                       (20, 45), 0.15)
            bolts.append((sub, 0.3))
    return bolts, start, end


def _draw_bolt_pass(size, bolts, color, width_mul, alpha, blur, core_width):
    layer = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for points, factor in bolts:
        width = max(1, round(core_width * factor * width_mul))
        a = int(alpha * (0.4 + 0.6 * factor))
        draw.line(points, fill=(*color, a), width=width, joint="curve")
    if blur > 0:
        layer = layer.filter(ImageFilter.GaussianBlur(blur))
    return layer


def _make_sky_flash(size, center):
    w, h = size
    radius = int(0.9 * max(w, h))
    peak = random.randint(60, 90)
    layer = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    cx, cy = center
    for r in range(radius, 0, -8):
        alpha = int(peak * (1 - r / radius))
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(220, 230, 255, alpha))
    return layer.filter(ImageFilter.GaussianBlur(radius * 0.03))


def _make_impact_glow(size, point):
    layer = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    x, y = point
    draw.ellipse((x - 60, y - 20, x + 60, y + 20), fill=(200, 215, 255, 60))
    draw.ellipse((x - 20, y - 6, x + 20, y + 6), fill=(255, 255, 255, 180))
    return layer.filter(ImageFilter.GaussianBlur(6))


def make_lightning_layer(size):
    """Молния: вспышка неба, ореол, свечение, белое ядро и блик в точке удара."""
    bolts, start, end = _lightning_bolts(size)
    core_width = random.randint(3, 4)
    layer = _make_sky_flash(size, start)
    for color, width_mul, alpha, blur in LIGHTNING_PASSES:
        layer = Image.alpha_composite(
            layer, _draw_bolt_pass(size, bolts, color, width_mul, alpha, blur, core_width))
    return Image.alpha_composite(layer, _make_impact_glow(size, end))


def make_rain_layer(seg, drop_count=400, lightning_chance=LIGHTNING_CHANCE):
    wind = random.uniform(0.2, 0.35)

    rain = Image.new('RGBA', seg.size, (20, 30, 40, min(45, drop_count // 25)))
    if random.random() < lightning_chance:
        rain = Image.alpha_composite(rain, make_lightning_layer(seg.size))
    for share, length_range, width, alpha_range, blur in RAIN_DEPTH_LAYERS:
        streaks = _draw_rain_streaks(seg.size, int(drop_count * share), length_range,
                                     width, alpha_range, wind, blur)
        rain = Image.alpha_composite(rain, streaks)
    rain = Image.alpha_composite(rain, _draw_splashes(seg.size, drop_count // 15))
    return Image.alpha_composite(seg, rain)


def get_clouds_layer(
        base,
        num_clouds: int = 15,
        cloud_size_range: tuple = (100, 200),
        opacity: int = 100,
        blur_radius: int = 15
):
    """
    Draw random cloud shapes on an image using Pillow.

    :param base: input image
    :param num_clouds: Number of clouds to draw
    :param cloud_size_range: Tuple (min_size, max_size) for cloud diameter
    :param opacity: Opacity of cloud fill (0-255)
    :param blur_radius: Gaussian blur radius to soften clouds
    """
    width, height = base.size

    # Create an RGBA layer for drawing clouds
    cloud_layer = Image.new("RGBA", base.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(cloud_layer)

    for _ in range(num_clouds):
        # Random center position for the cloud (y limited to sky region)
        cx = random.randint(0, width)
        cy = random.randint(0, height)

        # Random overall size of the cloud
        w = random.randint(*cloud_size_range)
        h = w // 2

        # Draw overlapping ellipses to form a cloud
        for _ in range(random.randint(3, 6)):
            ex = cx + random.randint(-w // 2, w // 2)
            ey = cy + random.randint(-h // 2, h // 2)
            ew = random.randint(w // 2, w)
            eh = random.randint(h // 2, h)
            draw.ellipse([ex, ey, ex + ew, ey + eh], fill=(255, 255, 255, opacity))

    # Apply a Gaussian blur to soften the cloud edges
    cloud_layer = cloud_layer.filter(ImageFilter.GaussianBlur(blur_radius))

    # Save the resulting image
    return cloud_layer


# доля, размер, цвет, alpha, длина следа, blur головы, blur следа
SNOW_LAYERS = [
    (0.60, (0.25, 0.50), (225, 235, 255), (55, 110), (0, 0), 1.2, 0),
    (0.32, (0.65, 1.00), (250, 252, 255), (100, 175), (3, 6), 0.3, 0.7),
    (0.08, (1.00, 1.35), (255, 255, 255), (135, 190), (6, 10), 0.45, 1.0),
]


def _draw_falling_snow_layer(
        image_size,
        count,
        flake_size_range,
        size_multiplier,
        color,
        alpha_range,
        trail_length_range,
        head_blur,
        trail_blur,
        wind,
        opacity_scale,
        blur_scale
):
    """Рисует каждую частицу один раз: отдельный след, затем компактную голову."""
    head_layer = Image.new("RGBA", image_size, (0, 0, 0, 0))
    trail_layer = Image.new("RGBA", image_size, (0, 0, 0, 0))
    heads = ImageDraw.Draw(head_layer)
    trails = ImageDraw.Draw(trail_layer)
    w, h = image_size

    for _ in range(count):
        x = random.uniform(-10, w + 10)
        y = random.uniform(-10, h + 10)
        flake_size = random.uniform(*flake_size_range) * random.uniform(*size_multiplier)
        alpha = min(255, int(random.randint(*alpha_range) * opacity_scale))
        particle_wind = wind + random.uniform(-0.06, 0.06)

        min_trail, max_trail = trail_length_range
        if max_trail > 0:
            trail_length = random.uniform(min_trail, max_trail)
            segments = 3
            line_width = max(1, round(flake_size * 0.22))
            for segment in range(segments):
                t0 = segment / segments
                t1 = (segment + 1) / segments
                x0 = x - particle_wind * trail_length * t0
                y0 = y - trail_length * t0
                x1 = x - particle_wind * trail_length * t1
                y1 = y - trail_length * t1
                trail_alpha = min(255, int((55 - 45 * t1) * opacity_scale))
                trails.line(
                    (x0, y0, x1, y1),
                    fill=(*color, trail_alpha),
                    width=line_width,
                )

        rx = flake_size * random.uniform(0.55, 0.85)
        ry = flake_size * random.uniform(0.70, 1.05)
        if max_trail > 0:
            heads.ellipse(
                (x - rx - 1, y - ry - 1, x + rx + 1, y + ry + 1),
                fill=(90, 105, 125, int(alpha * 0.35)),
            )
        heads.ellipse((x - rx, y - ry, x + rx, y + ry), fill=(*color, alpha))

    if trail_blur > 0 and blur_scale > 0:
        trail_layer = trail_layer.filter(
            ImageFilter.GaussianBlur(radius=trail_blur * blur_scale)
        )
    if head_blur > 0 and blur_scale > 0:
        head_layer = head_layer.filter(
            ImageFilter.GaussianBlur(radius=head_blur * blur_scale)
        )
    return Image.alpha_composite(trail_layer, head_layer)


def _low_frequency_noise(size, cell=24):
    width, height = size
    grid_w = max(2, width // cell)
    grid_h = max(2, height // cell)
    noise = Image.new("L", (grid_w, grid_h))
    noise.putdata([random.randint(0, 255) for _ in range(grid_w * grid_h)])
    noise = noise.resize(size, Image.Resampling.BICUBIC)
    return noise.filter(ImageFilter.GaussianBlur(max(1, cell // 3)))


def _draw_lane_ruts(size, lanes, strength):
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    color = (150, 158, 170, int(110 * strength))
    for x0, y0, x1, y1 in lanes:
        horizontal = (x1 - x0) >= (y1 - y0)
        if horizontal:
            mid = (y0 + y1) / 2
            offset = (y1 - y0) * 0.22
            for sign in (-1, 1):
                center = mid + sign * offset
                points = []
                x = x0
                while x <= x1:
                    points.append((x, center + math.sin(x / 40) * 2))
                    x += 8
                if len(points) > 1:
                    draw.line(points, fill=color, width=random.randint(7, 9))
        else:
            mid = (x0 + x1) / 2
            offset = (x1 - x0) * 0.22
            for sign in (-1, 1):
                center = mid + sign * offset
                points = []
                y = y0
                while y <= y1:
                    points.append((center + math.sin(y / 40) * 2, y))
                    y += 8
                if len(points) > 1:
                    draw.line(points, fill=color, width=random.randint(7, 9))
    return layer.filter(ImageFilter.GaussianBlur(2))


def make_snow_cover_layer(base, strength=1.0, lanes=(), keep_out=()):
    """Снег на асфальте: неровный покров, сугробы по краям, колеи и тёмный ореол номеров."""
    gray = base.convert("L")
    size = gray.size
    asphalt = gray.point(lambda p: 255 if p < 90 else 0)

    cover_alpha = int(195 * strength)
    noise = _low_frequency_noise(size)
    cover_mask = noise.point(lambda p, a=cover_alpha: int(a * (0.82 + 0.18 * p / 255)))
    cover_mask = ImageChops.multiply(cover_mask, asphalt)
    cover = Image.new("RGBA", size, (226, 232, 242, 0))
    cover.putalpha(cover_mask)

    edge = ImageChops.subtract(asphalt, asphalt.filter(ImageFilter.MinFilter(9)))
    edge = edge.filter(ImageFilter.GaussianBlur(4))
    drift_alpha = int(110 * strength)
    drift = Image.new("RGBA", size, (245, 248, 255, 0))
    drift.putalpha(edge.point(lambda p, a=drift_alpha: int(a * p / 255)))

    ruts = _draw_lane_ruts(size, lanes, strength)
    rut_bands = ruts.split()
    rut_alpha = ImageChops.multiply(rut_bands[3], asphalt)
    if keep_out:
        spots = Image.new("L", size, 0)
        spots_draw = ImageDraw.Draw(spots)
        for rect in keep_out:
            spots_draw.rectangle(rect, fill=255)
        allowed = ImageChops.invert(spots.filter(ImageFilter.GaussianBlur(2)))
        rut_alpha = ImageChops.multiply(rut_alpha, allowed)
    ruts = Image.merge("RGBA", (*rut_bands[:3], rut_alpha))

    bright = gray.point(lambda p: 255 if p > 200 else 0)
    text = ImageChops.multiply(bright, asphalt.filter(ImageFilter.MaxFilter(15)))
    halo_mask = ImageChops.subtract(text.filter(ImageFilter.MaxFilter(5)), text)
    halo_mask = halo_mask.filter(ImageFilter.GaussianBlur(0.8))
    halo = Image.new("RGBA", size, (45, 55, 70, 0))
    halo.putalpha(halo_mask.point(lambda p: int(170 * p / 255)))

    layer = Image.alpha_composite(cover, drift)
    layer = Image.alpha_composite(layer, ruts)
    return Image.alpha_composite(layer, halo)


def make_winter_tint(size, strength):
    """Холодный голубой свет на весь кадр."""
    return Image.new("RGBA", size, (205, 220, 245, int(22 * strength)))


def make_sun_warmth_layer(base, max_alpha=28):
    """Тёплый свет только на тёмной поверхности парковки."""
    asphalt = base.convert("L").point(lambda p: max_alpha if p < 90 else 0)
    layer = Image.new("RGBA", base.size, (255, 214, 150, 0))
    layer.putalpha(asphalt)
    return layer


def make_fog_layer(size):
    """Равномерная пелена: дальняя верхняя часть кадра скрыта сильнее."""
    width, height = size
    alpha = Image.new("L", (1, height))
    if height == 1:
        alpha.putpixel((0, 0), 100)
    else:
        alpha.putdata([
            int(130 - 60 * y / (height - 1))
            for y in range(height)
        ])
    alpha = alpha.resize(size)
    layer = Image.new("RGBA", size, (210, 214, 218, 0))
    layer.putalpha(alpha)
    return layer


def frost_car(car_image, strength):
    """Снежная шапка на верхней половине кузова."""
    car = car_image.convert("RGBA")
    width, height = car.size
    gradient = Image.new("L", (1, height))
    midpoint = max(1, height // 2)
    gradient.putdata([int(255 * (1 - y / midpoint)) if y < midpoint else 0 for y in range(height)])
    gradient = gradient.resize(car.size)
    mask = ImageChops.multiply(gradient, _low_frequency_noise(car.size, cell=6))
    cap_alpha = int(175 * strength)
    alpha = mask.point(lambda p, a=cap_alpha: int(a * p / 255))
    alpha = ImageChops.multiply(alpha, car.getchannel("A"))
    cap = Image.new("RGBA", car.size, (240, 244, 252, 0))
    cap.putalpha(alpha)
    return Image.alpha_composite(car, cap)


def add_snow(
        img: Union[str, Image.Image],
        snow_count: int = 500,
        snow_size_range: tuple = (2, 5),
        snow_opacity_range: tuple = (120, 220),
        snow_blur: float = 1.5,
        seed: int = None
) -> Image.Image:
    """Накладывает снег тремя слоями частиц с отдельными головами и следами."""
    if seed is not None:
        random.seed(seed)

    if isinstance(img, str):
        base = Image.open(img).convert("RGBA")
    else:
        base = img.convert("RGBA")

    wind = random.uniform(-0.35, -0.18)
    snow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    default_opacity_midpoint = 170
    opacity_midpoint = sum(snow_opacity_range) / 2
    opacity_scale = max(0.25, opacity_midpoint / default_opacity_midpoint)
    blur_scale = max(0, snow_blur / 1.5)

    for share, size_mul, color, alpha_range, trail_range, head_blur, trail_blur in SNOW_LAYERS:
        layer = _draw_falling_snow_layer(
            base.size,
            int(snow_count * share),
            snow_size_range,
            size_mul,
            color,
            alpha_range,
            trail_range,
            head_blur,
            trail_blur,
            wind,
            opacity_scale,
            blur_scale,
        )
        snow = Image.alpha_composite(snow, layer)

    return Image.alpha_composite(base, snow)


async def generate_weather_samples(output_dir: str = "pics/temp") -> None:
    """
    Строит карту парковки для каждого типа погоды и сохраняет PNG в pics/temp.
    Отрисовка та же, что в utils.map_generator.generate_parking_map.
    Запускать из корня проекта: python -m utils.weather_generator
    """
    import os
    from types import SimpleNamespace

    from models.parking_spot import SpotStatus
    from services.weather_service import weather_map
    from utils.map_generator import generate_parking_map

    os.makedirs(output_dir, exist_ok=True)

    spots = [
        SimpleNamespace(
            id=spot_id, x=0, y=0, width=40, height=80,
            status=SpotStatus.OCCUPIED,
            current_driver_id=index + 1,
            current_driver=None,
        )
        for index, spot_id in enumerate((3, 8, 14, 22, 30, 40, 46, 74))
    ]

    samples = []
    for code, weather in weather_map.items():
        temp = "-8°" if weather.get("snow_count", 0) > 0 else "+12°"
        samples.append((code, temp, dict(weather)))
    # Минус в температуре рисует снег вместо капель, без снеговика
    samples.append(("10_frost", "-4°", dict(weather_map["10"])))
    samples.append(("11_lightning", "+12°", {**weather_map["11"], "lightning_chance": 1.0}))
    samples.append(("01_winter", "-12°", dict(weather_map["01"])))
    samples.append(("04_winter", "-5°", dict(weather_map["04"])))

    for code, temp, weather in samples:
        img = await generate_parking_map(
            spots,
            None,
            None,
            weather_override=(temp, weather, code),
        )
        path = os.path.join(output_dir, f"weather_{code}.png")
        img.save(path)
        print(path)


if __name__ == "__main__":
    import asyncio

    asyncio.run(generate_weather_samples())
