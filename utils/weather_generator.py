import math
import os
import random
from typing import Union

from PIL import Image, ImageChops
from PIL import ImageDraw, ImageFilter


def make_sun_glare_layer(size, center=None, max_alpha=120, radius=None):
    """
    Создаёт слой «солнечного» градиента на весь кадр.

    Градиент строится на уменьшенной маске и затем масштабируется обратно.
    Это сохраняет мягкое мультяшное свечение, но сокращает количество
    операций с концентрическими окружностями на большой карте.
    """
    w, h = size
    if center is None:
        center = (w * 0.3, h * 0.2)  # сверху слева
    if radius is None:
        radius = int(max(w, h) * 1.05)

    # На текущей карте 941x1672 это уменьшает рабочую маску примерно
    # в 9 раз по площади и заметно ускоряет отрисовку.
    render_scale = max(1, min(4, max(w, h) // 512))
    small_size = (
        max(1, (w + render_scale - 1) // render_scale),
        max(1, (h + render_scale - 1) // render_scale),
    )
    small_center = (center[0] / render_scale, center[1] / render_scale)
    small_radius = max(1, int(radius / render_scale))

    alpha_mask = Image.new("L", small_size, 0)
    draw = ImageDraw.Draw(alpha_mask)
    # Концентрические круги строятся на маленькой маске, затем сглаживаются
    # при увеличении до исходного размера.
    for r in range(small_radius, 0, -1):
        alpha = int(max_alpha * (1 - r / small_radius))
        bbox = [
            (small_center[0] - r, small_center[1] - r),
            (small_center[0] + r, small_center[1] + r),
        ]
        draw.ellipse(bbox, fill=alpha)

    alpha_mask = alpha_mask.resize(size, Image.Resampling.LANCZOS)
    layer = Image.new("RGBA", size, (255, 255, 200, 0))
    layer.putalpha(alpha_mask)
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
        blur_radius: int = 15,
        cloud_color: tuple = (255, 255, 255),
        shadow_color: tuple = (72, 88, 112),
        shadow_offset: tuple = (14, 18),
        shadow_opacity: int = 42,
        shadow_blur_radius: int = 24,
        seed=None,
):
    """
    Draw random cloud shapes on an image using Pillow.

    :param base: input image
    :param num_clouds: Number of clouds to draw
    :param cloud_size_range: Tuple (min_size, max_size) for cloud diameter
    :param opacity: Opacity of cloud fill (0-255)
    :param blur_radius: Gaussian blur radius to soften clouds
    :param cloud_color: Цвет мультяшной массы облака
    :param shadow_color: Цвет мягкой тени под облаком
    :param shadow_offset: Смещение мультяшной тени облака по x/y
    :param shadow_opacity: Прозрачность тени облака
    :param shadow_blur_radius: Радиус размытия тени
    """
    width, height = base.size
    rng = random.Random(seed)

    # Облака и их тени рисуются из одной геометрии. Смещённая серо-синяя
    # тень помогает облакам восприниматься над картой, а не белыми пятнами
    # непосредственно на асфальте.
    cloud_layer = Image.new("RGBA", base.size, (255, 255, 255, 0))
    shadow_layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    clouds = ImageDraw.Draw(cloud_layer)
    shadows = ImageDraw.Draw(shadow_layer)
    shadow_dx, shadow_dy = shadow_offset

    for _ in range(num_clouds):
        cx = rng.randint(0, width)
        cy = rng.randint(0, height)

        w = rng.randint(*cloud_size_range)
        h = w // 2

        for _ in range(rng.randint(3, 6)):
            ex = cx + rng.randint(-w // 2, w // 2)
            ey = cy + rng.randint(-h // 2, h // 2)
            ew = rng.randint(w // 2, w)
            eh = rng.randint(h // 2, h)
            ellipse = (ex, ey, ex + ew, ey + eh)
            shadows.ellipse(
                (
                    ellipse[0] + shadow_dx,
                    ellipse[1] + shadow_dy,
                    ellipse[2] + shadow_dx,
                    ellipse[3] + shadow_dy,
                ),
                fill=(*shadow_color, shadow_opacity),
            )
            clouds.ellipse(ellipse, fill=(*cloud_color, opacity))

    shadow_layer = shadow_layer.filter(
        ImageFilter.GaussianBlur(shadow_blur_radius)
    )
    cloud_layer = cloud_layer.filter(ImageFilter.GaussianBlur(blur_radius))
    return Image.alpha_composite(shadow_layer, cloud_layer)


# Доля, размер, цвет, alpha, длина следа, blur головы, blur следа.
# Пять планов дают снегу более выраженную глубину: от мелкой снежной пыли
# вдали до крупных хлопьев прямо перед камерой.
SNOW_LAYERS = [
    (0.30, (0.18, 0.35), (215, 228, 250), (40, 85), (0, 0), 1.6, 0),
    (0.25, (0.32, 0.55), (225, 235, 255), (55, 115), (0, 2), 1.1, 0.2),
    (0.22, (0.55, 0.85), (240, 247, 255), (85, 150), (2, 5), 0.55, 0.5),
    (0.15, (0.80, 1.10), (250, 252, 255), (110, 180), (4, 8), 0.35, 0.8),
    (0.08, (1.10, 1.50), (255, 255, 255), (145, 210), (7, 12), 0.5, 1.1),
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
        blur_scale,
        rng=None,
):
    """Рисует каждую частицу один раз: отдельный след, затем компактную голову."""
    rng = rng or random
    head_layer = Image.new("RGBA", image_size, (0, 0, 0, 0))
    trail_layer = Image.new("RGBA", image_size, (0, 0, 0, 0))
    heads = ImageDraw.Draw(head_layer)
    trails = ImageDraw.Draw(trail_layer)
    w, h = image_size

    for _ in range(count):
        x = rng.uniform(-10, w + 10)
        y = rng.uniform(-10, h + 10)
        flake_size = rng.uniform(*flake_size_range) * rng.uniform(*size_multiplier)
        alpha = min(255, int(rng.randint(*alpha_range) * opacity_scale))
        particle_wind = wind + rng.uniform(-0.06, 0.06)

        min_trail, max_trail = trail_length_range
        if max_trail > 0:
            trail_length = rng.uniform(min_trail, max_trail)
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

        rx = flake_size * rng.uniform(0.55, 0.85)
        ry = flake_size * rng.uniform(0.70, 1.05)
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


def _low_frequency_noise(size, cell=24, rng=None):
    rng = rng or random
    width, height = size
    grid_w = max(2, width // cell)
    grid_h = max(2, height // cell)
    noise = Image.new("L", (grid_w, grid_h))
    noise.putdata([rng.randint(0, 255) for _ in range(grid_w * grid_h)])
    noise = noise.resize(size, Image.Resampling.BICUBIC)
    return noise.filter(ImageFilter.GaussianBlur(max(1, cell // 3)))


def _draw_polyline_ruts(draw, path, width, strength):
    """Draw two soft tire tracks around a road centerline."""
    if len(path) < 2:
        return

    points = [(float(x), float(y)) for x, y in path]
    left = []
    right = []
    for index, (x, y) in enumerate(points):
        before = points[max(0, index - 1)]
        after = points[min(len(points) - 1, index + 1)]
        tangent_x = after[0] - before[0]
        tangent_y = after[1] - before[1]
        length = math.hypot(tangent_x, tangent_y) or 1
        normal_x = -tangent_y / length
        normal_y = tangent_x / length
        offset = 13
        left.append((x + normal_x * offset, y + normal_y * offset))
        right.append((x - normal_x * offset, y - normal_y * offset))

    color = (150, 158, 170, int(105 * strength))
    draw.line(left, fill=color, width=width, joint="curve")
    draw.line(right, fill=color, width=width, joint="curve")


def _draw_lane_ruts(size, lanes, strength, rng=None):
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    rng = rng or random
    for lane in lanes:
        # New map geometry is represented by centerline polylines. Keep support
        # for the old 4-point segments so the helper remains backwards compatible.
        if lane and isinstance(lane[0], (tuple, list)):
            _draw_polyline_ruts(draw, lane, width=max(5, round(9 * strength)), strength=strength)
            continue

        x0, y0, x1, y1 = lane
        color = (150, 158, 170, int(105 * strength))
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
                    draw.line(points, fill=color, width=rng.randint(7, 9))
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
                    draw.line(points, fill=color, width=rng.randint(7, 9))
    return layer.filter(ImageFilter.GaussianBlur(2))


def _snow_cover_parts(
        base,
        strength=1.0,
        lanes=(),
        keep_out=(),
        seed=None,
        surface_mask=None,
):
    """Build the winter surface layers and masks for rendering/debugging."""
    rng = random.Random(seed)
    gray = base.convert("L")
    size = gray.size
    # map3.png has a textured, illustrated asphalt instead of the nearly
    # uniform dark surface of the previous map. A soft threshold keeps that
    # texture from turning into jagged black/white islands under the snow.
    raw_asphalt = gray.point(
        lambda p: (
            255
            if p <= 82
            else max(0, round((138 - p) * 255 / 56))
        )
    )
    asphalt = raw_asphalt
    if surface_mask is not None:
        asphalt = ImageChops.multiply(asphalt, surface_mask.convert("L"))

    cover_alpha = int(195 * strength)
    noise = _low_frequency_noise(size, rng=rng)
    cover_mask = noise.point(lambda p, a=cover_alpha: int(a * (0.82 + 0.18 * p / 255)))
    cover_mask = ImageChops.multiply(cover_mask, asphalt)
    cover = Image.new("RGBA", size, (226, 232, 242, 0))
    cover.putalpha(cover_mask)

    edge = ImageChops.subtract(
        raw_asphalt,
        raw_asphalt.filter(ImageFilter.MinFilter(9)),
    )
    if surface_mask is not None:
        edge = ImageChops.multiply(edge, surface_mask.convert("L"))
    edge = edge.filter(ImageFilter.GaussianBlur(4))
    drift_alpha = int(110 * strength)
    drift = Image.new("RGBA", size, (245, 248, 255, 0))
    drift.putalpha(edge.point(lambda p, a=drift_alpha: int(a * p / 255)))

    ruts = _draw_lane_ruts(size, lanes, strength, rng=rng)
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

    return {
        "surface_mask": (
            surface_mask.convert("L")
            if surface_mask is not None
            else Image.new("L", size, 255)
        ),
        "asphalt_mask": asphalt,
        "cover_mask": cover_mask,
        "edge_mask": edge,
        "keep_out_mask": spots if keep_out else Image.new("L", size, 0),
        "rut_mask": rut_alpha,
        "cover": cover,
        "drift": drift,
        "ruts": ruts,
        "halo": halo,
    }


def save_winter_debug_masks(parts, output_dir):
    """Save the masks used by the winter renderer for visual calibration."""
    os.makedirs(output_dir, exist_ok=True)
    for name in (
            "surface_mask",
            "asphalt_mask",
            "cover_mask",
            "edge_mask",
            "keep_out_mask",
            "rut_mask",
    ):
        parts[name].save(os.path.join(output_dir, f"winter_{name}.png"))


def make_snow_cover_layer(
        base,
        strength=1.0,
        lanes=(),
        keep_out=(),
        seed=None,
        surface_mask=None,
        debug_dir=None,
):
    """Снег на асфальте: неровный покров, сугробы по краям и колеи."""
    parts = _snow_cover_parts(
        base,
        strength,
        lanes,
        keep_out,
        seed,
        surface_mask,
    )
    if debug_dir:
        save_winter_debug_masks(parts, debug_dir)

    layer = Image.alpha_composite(parts["cover"], parts["drift"])
    layer = Image.alpha_composite(layer, parts["ruts"])
    return Image.alpha_composite(layer, parts["halo"])


def make_winter_tint(size, strength):
    """Холодный голубой свет на весь кадр."""
    # Не выбеливаем новую карту: холодный оттенок должен ощущаться только
    # как лёгкая цветокоррекция поверх снега и фона.
    return Image.new("RGBA", size, (195, 210, 232, int(12 * strength)))


def make_sun_warmth_layer(base, max_alpha=28):
    """Тёплый свет только на тёмной поверхности парковки."""
    asphalt = base.convert("L").point(lambda p: max_alpha if p < 90 else 0)
    layer = Image.new("RGBA", base.size, (255, 214, 150, 0))
    layer.putalpha(asphalt)
    return layer


def make_fog_layer(size, seed=None):
    """Туман для вида сверху: ровная дымка и неоднородные мягкие сгустки."""
    rng = random.Random(seed)

    # Тонкая общая пелена приглушает контраст всей карты без привязки
    # к верху/низу кадра — у карты с видом сверху нет горизонта.
    veil = Image.new("RGBA", size, (205, 213, 222, 42))

    # Крупные туманные поля создают основную неоднородность.
    broad_noise = _low_frequency_noise(size, cell=180, rng=rng)
    broad_alpha = broad_noise.point(lambda p: 10 + round(50 * p / 255))
    broad = Image.new("RGBA", size, (218, 224, 231, 0))
    broad.putalpha(broad_alpha)

    # Более компактные плотные сгустки появляются только на светлых участках
    # второй шумовой маски и не образуют узнаваемых «облаков».
    local_noise = _low_frequency_noise(size, cell=85, rng=rng)
    local_alpha = local_noise.point(
        lambda p: 0 if p <= 120 else round(62 * (p - 120) / 135)
    )
    local_alpha = local_alpha.filter(ImageFilter.GaussianBlur(18))
    local = Image.new("RGBA", size, (230, 234, 239, 0))
    local.putalpha(local_alpha)

    fog = Image.alpha_composite(veil, broad)
    return Image.alpha_composite(fog, local)


def frost_car(car_image, strength, seed=None):
    """Снежная шапка на верхней половине кузова."""
    car = car_image.convert("RGBA")
    width, height = car.size
    gradient = Image.new("L", (1, height))
    midpoint = max(1, height // 2)
    gradient.putdata([int(255 * (1 - y / midpoint)) if y < midpoint else 0 for y in range(height)])
    gradient = gradient.resize(car.size)
    mask = ImageChops.multiply(
        gradient,
        _low_frequency_noise(car.size, cell=6, rng=random.Random(seed)),
    )
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
        seed: int = None,
) -> Image.Image:
    """Накладывает снег тремя слоями частиц с отдельными головами и следами."""
    if isinstance(img, str):
        base = Image.open(img).convert("RGBA")
    else:
        base = img.convert("RGBA")

    rng = random.Random(seed)
    wind = rng.uniform(-0.35, -0.18)
    snow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    default_opacity_midpoint = 170
    opacity_midpoint = sum(snow_opacity_range) / 2
    opacity_scale = max(0.25, opacity_midpoint / default_opacity_midpoint)
    blur_scale = max(0, snow_blur / 1.5)

    requested_count = max(0, int(snow_count))
    remaining_count = requested_count
    for index, (
            share,
            size_mul,
            color,
            alpha_range,
            trail_range,
            head_blur,
            trail_blur,
    ) in enumerate(SNOW_LAYERS):
        # Последний слой получает остаток, чтобы из-за округления не терялись
        # снежинки при распределении по большему количеству планов.
        layer_count = (
            remaining_count
            if index == len(SNOW_LAYERS) - 1
            else min(remaining_count, round(requested_count * share))
        )
        remaining_count -= layer_count
        layer = _draw_falling_snow_layer(
            base.size,
            layer_count,
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
            rng,
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
            current_driver_id=index + 1 + random.randint(0, 50),
            current_driver=None,
        )
        for index, spot_id in enumerate((3, 8, 14, 22, 30, 40, 46, 74, 2, 2, 4, 4, 52, 52, 68, 68, 66, 66, 65, 65))
    ]
    queue_entries = [
        SimpleNamespace(
            driver=SimpleNamespace(id=index + 1, attributes={"car_index": car_index}),
            spot_id=None,
        )
        for index, car_index in enumerate((5, 18, 42))
    ]

    samples = []
    for code, weather in weather_map.items():
        temp = "-8°" if weather.get("snow_count", 0) > 0 else "+12°"
        samples.append((code, temp, dict(weather)))
    # Минус в температуре рисует снег вместо капель, без снеговика
    samples.append(("10_frost", "-4°", dict(weather_map["10"])))
    samples.append(("11_lightning", "+12°", {**weather_map["11"], "lightning_chance": 1.0}))
    samples.append((
        "01_winter",
        "-12°",
        {**weather_map["01"], "debug_winter_masks_dir": output_dir},
    ))
    samples.append((
        "04_winter",
        "-5°",
        {**weather_map["04"], "debug_winter_masks_dir": output_dir},
    ))

    for code, temp, weather in samples:
        img = await generate_parking_map(
            spots,
            None,
            None,
            weather_override=(temp, weather, code),
            labels_above_cars=False,
            queue_entries=queue_entries,
        )
        path = os.path.join(output_dir, f"weather_{code}.png")
        img.save(path)
        print(path)


if __name__ == "__main__":
    import asyncio

    asyncio.run(generate_weather_samples())
