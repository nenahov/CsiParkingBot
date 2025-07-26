import random

from PIL import Image, ImageDraw, ImageFilter, ImageChops


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


def make_rain_layer(seg, drop_count=400):
    layer = Image.new('RGBA', seg.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    w, h = seg.size
    for _ in range(drop_count):
        x = random.randint(0, w)
        y = random.randint(0, h)
        length = random.randint(10, 20)
        # угол падения ~70° (около 1.2 радиан)
        dx = -int(length * 0.34)
        dy = int(length * 0.94)
        draw.line((x, y, x + dx, y + dy), fill=(66, 170, 255, random.randint(200, 255)), width=2)
    rain = layer.filter(ImageFilter.GaussianBlur(1))

    # Молния с небольшой вероятностью
    if random.random() < 0.01:
        bolt = Image.new('RGBA', seg.size, (0, 0, 0, 0))
        ldraw = ImageDraw.Draw(bolt)

        def draw_branch(x0, y0, length, thickness, segments, branch_chance):
            """Рекурсивно рисует ветку молнии."""
            if segments <= 0 or thickness < 1:
                return
            # координата следующей точки
            x1 = x0 + random.randint(-w // 10, w // 10)
            y1 = y0 + length + random.randint(-h // 20, h // 20)
            ldraw.line((x0, y0, x1, y1), fill=(255, 255, 220, 200), width=thickness)

            # шанс ветвления
            if random.random() < branch_chance:
                # боковая ветка
                draw_branch(x1, y1,
                            length // 2,
                            max(1, thickness - 2),
                            segments - 1,
                            branch_chance * 0.6)
            # продолжение ствола
            draw_branch(x1, y1,
                        length,
                        thickness,
                        segments - 1,
                        branch_chance)

        # параметры молнии
        start_x = random.randint(int(w * 0.2), int(w * 0.8))
        start_y = 0
        main_length = h // random.randint(segments := 5, 6)
        main_thickness = random.randint(4, 6)
        draw_branch(start_x, start_y,
                    length=main_length,
                    thickness=main_thickness,
                    segments=6,  # глубина рекурсии
                    branch_chance=0.7)  # начальный шанс ветвления

        bolt = bolt.filter(ImageFilter.GaussianBlur(1))
        # Объединяем дождь и молнию
        rain = Image.alpha_composite(rain, bolt)
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
