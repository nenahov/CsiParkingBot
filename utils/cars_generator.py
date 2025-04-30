import io
import random

import numpy as np
from PIL import Image, ImageDraw, ImageOps, ImageFilter
from moviepy import ImageSequenceClip

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
    current_index = current_index % cars_count
    return extract_sprite(cars3, (50 * (current_index % 12), 100 * (current_index // 12),
                                  50 * (1 + (current_index % 12)), 100 * (1 + (current_index // 12))))


def extract_sprite(sprite_sheet, sprite_rect):
    """
    Извлекает спрайт из спрайт-листа.

    :param sprite_sheet: Изображение со спрайт-листом (PIL Image)
    :param sprite_rect: Кортеж (left, top, right, bottom), задающий область спрайта
    :return: Извлечённое изображение спрайта
    """
    return sprite_sheet.crop(sprite_rect)


def draw_race_track(lane_count=4, lane_height=70, track_length=800,
                    bg_color=(50, 50, 50), separator_color=(255, 255, 255),
                    start_color=(0, 200, 0), finish_color=(200, 0, 0),
                    separator_width=2, boundary_width=5):
    """
    Рисует прямую гоночную трассу.

    :param lane_count: число полос
    :param lane_height: высота одной полосы в пикселях
    :param track_length: длина трассы в пикселях
    :param bg_color: цвет фона трассы (RGB)
    :param separator_color: цвет разделительных линий (RGB)
    :param start_color: цвет линии старта (RGB)
    :param finish_color: цвет линии финиша (RGB)
    :param separator_width: ширина разделительных линий
    :param boundary_width: ширина линий старта/финиша
    """
    img_height = lane_count * lane_height
    img = Image.new('RGB', (track_length, img_height), bg_color)
    draw = ImageDraw.Draw(img)

    # Разметка полос: горизонтальные линии
    for i in range(1, lane_count):
        y = i * lane_height
        draw.line([(0, y), (track_length, y)], fill=separator_color, width=separator_width)

    # for i in range(0, lane_count):
    #     y = i * lane_height
    #     car_image = get_car(random.randint(0, cars_count - 1))
    #     car_image = car_image.rotate(270, expand=True)
    #     img.paste(car_image, (1, y + 8), mask=car_image)

    # Линия старта – слева
    draw.line([(105, 0), (105, img_height)], fill=start_color, width=boundary_width)
    # Линия финиша – справа
    draw.line([(track_length - 1, 0), (track_length - 1, img_height)], fill=finish_color, width=boundary_width)
    return img


def create_race_gif(cars_icons, output_path='race.gif', frame_count=50, duration=100):
    """
    Создаёт GIF с "гонкой" машин по нарисованной трассе.

    :param output_path: куда сохранить итоговый GIF
    :param frame_count: число кадров в анимации
    :param duration: длительность одного кадра в миллисекундах
    """
    # Загружаем изображения машин
    car_w, car_h = (100, 50)
    lane_count = len(cars_icons)

    # Рисуем фон — трассу
    track = draw_race_track(lane_count=lane_count,
                            lane_height=70,
                            bg_color=(120, 120, 120),
                            track_length=1800).convert('RGBA')

    max_x = float(track.width - car_w)
    # Различные базовые скорости для разнообразия гонки
    speed_factors = [1.0 + random.uniform(0, 0.7) for _ in range(lane_count)]
    base_speeds = [max_x / frame_count * f for f in speed_factors]
    positions = [0.0] * lane_count
    np_frames = []
    winners = list()
    frames = []
    for _ in range(frame_count):
        frame = track.copy()
        for idx in range(0, lane_count):
            car = get_car(cars_icons[idx])
            car = car.rotate(270, expand=True)
            part_before = 3 * positions[idx] // max_x
            positions[idx] = positions[idx] + base_speeds[idx]
            x = int(positions[idx])
            part_after = 3 * positions[idx] // max_x
            if part_before != part_after:
                speed = 1.0 + random.uniform(0, 0.7)
                base_speeds[idx] = max_x / frame_count * speed
            # Вертикаль: центрируем машину в своей полосе
            y = idx * 70 + (70 - car_h) // 2
            draw_car_with_shadow(car, frame, x, y)
            if positions[idx] >= max_x:
                draw_car_with_shadow(car, frame, 0, y)
                if idx not in winners:
                    winners.append(idx)
        # Для GIF конвертируем в P-палитру
        frames.append(frame.convert('P'))
        np_frames.append(np.asarray(frame))

    # Сохраняем в GIF
    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        duration=duration,
        loop=0
    )
    print(f"Сохранено: {output_path}")
    print(*[w + 1 for w in winners])

    clip = ImageSequenceClip(np_frames, fps=60)
    clip.write_videofile(
        "race.mp4",
        codec="libx264",
        ffmpeg_params=["-movflags", "faststart"],
        audio=False
    )


def draw_car_with_shadow(car_image, frame, car_x, car_y):
    # Создаем тень
    shadow = Image.new("RGBA", car_image.size, (0, 0, 0, 0))
    shadow.putalpha(car_image.split()[3])
    shadow = ImageOps.colorize(shadow.convert("L"), black="black", white="black")
    shadow.putalpha(car_image.split()[3])
    blur_radius = 10  # радиус размытия тени
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur_radius))

    # Смещаем тень относительно машины
    shadow_position = (car_x + 5, car_y + 5)

    # Накладываем тень
    frame.paste(shadow, shadow_position, mask=car_image)
    frame.paste(car_image, (car_x, car_y), car_image)


if __name__ == "__main__":
    # Пример: 5 полос
    # track = draw_race_track(lane_count=5)
    # track.save("race_track.png")
    # track.show()
    create_race_gif(cars_icons=[0, 5, 7, 11, 27, 135, 12, 1, 2, 3],
                    output_path="race.gif", frame_count=400, duration=2)
