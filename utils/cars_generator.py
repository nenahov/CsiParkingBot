import io

from PIL import Image

cars3 = Image.open("./pics/cars3.png").convert("RGBA")
cars_count = 24


def reduce_opacity(image: Image.Image, opacity: float) -> Image.Image:
    """
    Уменьшает прозрачность изображения, изменяя его альфа-канал.
    """
    if image.mode != 'RGBA':
        image = image.convert('RGBA')
    alpha = image.split()[3].point(lambda p: int(p * opacity))
    image.putalpha(alpha)
    return image


def generate_carousel_image(current_index: int) -> io.BytesIO:
    """
    Генерирует изображение карусели из 7 спрайтов.

    Спрайты располагаются горизонтально с наложением.
    Коэффициенты масштабирования и прозрачности зависят от расстояния
    от центра:
      смещение 0: scale=1.0, opacity=1.0
      смещение ±1: scale=0.8, opacity=0.8
      смещение ±2: scale=0.6, opacity=0.6
      смещение ±3: scale=0.4, opacity=0.4
    """
    # Задаем коэффициенты для смещений (по модулю)
    scale_factors = {0: 1.0, 1: 0.75, 2: 0.7, 3: 0.7}
    # Смещения относительно центрального спрайта
    offsets = [-3, -2, -1, 0, 1, 2, 3]
    # offsets = [-2, -1, 0, 1, 2]

    # Открываем центральное изображение для базового размера
    center_img = get_car(current_index)
    base_w, base_h = center_img.size

    # Задаем шаг между центрами спрайтов.
    # Если шаг меньше базовой ширины, изображения будут частично перекрываться.
    step = int(base_w * 0.8)  # эмпирически подобранное значение

    # Определяем центры по горизонтали относительно условного 0
    centers_x = {off: off * step for off in offsets}

    # Сохраним данные для каждого спрайта: изображение, масштаб, размеры, центр
    sprite_data = {}
    left_extents = []
    right_extents = []
    for off in offsets:
        scale = scale_factors[abs(off)]
        idx = (current_index + off) % cars_count
        img = get_car(idx)
        new_size = (int(base_w * scale), int(base_h * scale))
        img = img.resize(new_size)  # , Image.ANTIALIAS)
        if off != 0:
            img = reduce_opacity(img, 0.7)  # используем масштаб как коэффициент прозрачности
        sprite_data[off] = {
            "img": img,
            "size": new_size,
            "center_x": centers_x[off],
            "center_y": base_h // 2  # выравниваем по вертикали относительно базового размера
        }
        half_w = new_size[0] // 2
        left_extents.append(centers_x[off] - half_w)
        right_extents.append(centers_x[off] + half_w)

    # Сдвигаем координаты так, чтобы они были положительными
    min_x = min(left_extents)
    shift = -min_x

    # Определяем ширину полотна (canvas) по максимальному правому краю
    max_x = max(right_extents)
    canvas_width = max_x + shift
    canvas_height = base_h  # базовая высота

    canvas = Image.new("RGBA", (canvas_width, canvas_height), (15, 15, 15, 210))

    # Для обеспечения правильного наложения рисуем спрайты в порядке увеличения близости к центру.
    for off in sorted(offsets, key=lambda x: abs(x), reverse=True):
        data = sprite_data[off]
        img = data["img"]
        cx = data["center_x"] + shift
        cy = data["center_y"]
        top_left = (cx - data["size"][0] // 2, cy - data["size"][1] // 2)
        canvas.paste(img, top_left, img)

    bio = io.BytesIO()
    canvas.save(bio, format="PNG")
    bio.seek(0)
    return bio


def get_car(current_index):
    return extract_sprite(cars3, (50 * (current_index % 12), 100 * (current_index % 2),
                                  50 * (1 + (current_index % 12)), 100 * (1 + (current_index % 2))))


def extract_sprite(sprite_sheet, sprite_rect):
    """
    Извлекает спрайт из спрайт-листа.

    :param sprite_sheet: Изображение со спрайт-листом (PIL Image)
    :param sprite_rect: Кортеж (left, top, right, bottom), задающий область спрайта
    :return: Извлечённое изображение спрайта
    """
    return sprite_sheet.crop(sprite_rect)
