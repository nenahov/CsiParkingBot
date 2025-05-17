import io
import random

import numpy as np
from PIL import Image, ImageDraw, ImageOps, ImageFilter, ImageFont
from moviepy import ImageSequenceClip

from utils.weather_generator import make_sun_glare_layer, get_clouds_layer, add_edge_fade_mask, make_rain_layer

cars3 = Image.open("./pics/cars3.png").convert("RGBA")
cars_count = 24
extra_cars_count = 29
regular_font = ImageFont.truetype("ariali.ttf", 40)
car_w, car_h = (100, 50)
finish_block_size = 5


def reduce_opacity(image: Image.Image, opacity: float) -> Image.Image:
    """
    Уменьшает прозрачность изображения, изменяя его альфа-канал.
    """
    if image.mode != 'RGBA':
        image = image.convert('RGBA')
    alpha = image.split()[3].point(lambda p: int(p * opacity))
    image.putalpha(alpha)
    return image


def generate_carousel_image(current_index: int, cars_count_for_driver: int) -> io.BytesIO:
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
        idx = (current_index + off) % cars_count_for_driver
        img = get_car(idx)
        new_size = (int(base_w * scale), int(base_h * scale))
        img = img.resize(new_size)  # , Image.ANTIALIAS)
        if off != 0:
            img = reduce_opacity(img, 0.7)  # коэффициент прозрачности
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
    current_index = current_index
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


def draw_race_track(players, lane_height=70, track_length=800,
                    bg_color=(50, 50, 50), separator_color=(220, 220, 0),
                    start_color=(220, 220, 220), separator_width=2, boundary_width=5,
                    stripe_height=5, stripe_width=20):
    """
    Рисует прямую гоночную трассу с декоративными элементами:
    - Красно-белые полосы вдоль верхнего и нижнего края
    - Прерывистые разделительные линии между полосами
    - Чекер-финиш: две колонки черно-белых квадратов
    """
    img_height = len(players) * lane_height
    img = Image.new('RGB', (track_length, img_height), bg_color)
    draw = ImageDraw.Draw(img)

    # Линия старта – слева
    draw.line([(105, 0), (105, img_height)], fill=start_color, width=boundary_width)

    # Верхние и нижние красно-белые полосы
    for x in range(0, track_length, stripe_width * 2):
        # Красный
        draw.rectangle([x, 0, x + stripe_width, stripe_height], fill=(200, 0, 0))
        draw.rectangle([x, img_height - stripe_height, x + stripe_width, img_height], fill=(200, 0, 0))
        # Белый
        draw.rectangle([x + stripe_width, 0, x + stripe_width * 2, stripe_height], fill=(255, 255, 255))
        draw.rectangle([x + stripe_width, img_height - stripe_height, x + stripe_width * 2, img_height],
                       fill=(255, 255, 255))

    # Прерывистые разделительные линии
    dash_len = 20
    gap_len = 10
    for i in range(1, len(players)):
        y = i * lane_height
        x = 0
        # Рисуем штрихи
        while x < track_length:
            x_end = min(x + dash_len, track_length)
            draw.line([(x, y), (x_end, y)], fill=separator_color, width=separator_width)
            x += dash_len + gap_len

    # Имена участников и машины
    for idx, player in enumerate(players):
        y_text = idx * lane_height + (lane_height - 40) // 2
        draw.text((car_w + 25, y_text), text=player.title, font=regular_font, fill=(200, 200, 200))

    # Чекер-финиш – справа, две колонки квадратов
    blocks_vertical = (img_height + finish_block_size - 1) // finish_block_size
    finish_x = track_length - finish_block_size * 2
    for col in range(2):
        for row in range(blocks_vertical):
            x0 = finish_x + col * finish_block_size
            y0 = row * finish_block_size
            x1 = x0 + finish_block_size
            y1 = min(y0 + finish_block_size, img_height)
            # Чередование цвета
            if (row + col) % 2 == 0:
                fill = (0, 0, 0)
            else:
                fill = start_color
            draw.rectangle([x0, y0, x1, y1], fill=fill)

    return img


def draw_start_race_track(players, lane_height=70, track_length=800,
                          bg_color=(50, 50, 50)):
    """
    Рисует прямую гоночную трассу с машинами на старте.
    """
    img = draw_race_track(players, lane_height=lane_height,
                          track_length=track_length,
                          bg_color=bg_color)
    for idx, player in enumerate(players):
        y = idx * 70 + (70 - car_h) // 2
        car = get_car(player.attributes.get("car_index", player.id % cars_count))
        car = car.rotate(270, expand=True)
        draw_car_with_shadow(car, img, 0, y)
    return img


def create_race_gif(players, chat_id: int, output_path='race.gif', frame_count=50, duration=100):
    """
    Создаёт GIF с "гонкой" машин по нарисованной трассе.

    :param output_path: куда сохранить итоговый GIF
    :param frame_count: число кадров в анимации
    :param duration: длительность одного кадра в миллисекундах
    """
    # Загружаем изображения машин
    lane_count = len(players)

    # Рисуем фон — трассу
    track = draw_race_track(players=players,
                            lane_height=70,
                            bg_color=(120, 120, 120),
                            track_length=1800).convert('RGBA')
    max_x = float(track.width - car_w)
    # Различные базовые скорости для разнообразия гонки
    speed_factors = [1.0 for _ in range(lane_count)]
    base_speeds = [(max_x + car_w) / frame_count * f for f in speed_factors]
    # погодный фактор скорости
    weather_factor = [-1001.0 for _ in range(lane_count)]
    positions = [0.0] * lane_count
    np_frames = []
    winners = list()
    frames = []
    seg_count = 3
    type_segs = random.choices(population=range(3), k=seg_count)
    print(type_segs)
    sunny_segs = [idx for idx, t in enumerate(type_segs) if t == 2]
    sun_layer = make_sun_glare_layer((track.width, track.height), max_alpha=100)
    sun_layer = add_edge_fade_mask(sun_layer, sunny_segs, seg_count=seg_count)
    track = Image.alpha_composite(track, sun_layer)
    cloud_layer = get_clouds_layer(track)
    cloudy_segs = [idx for idx, t in enumerate(type_segs) if t != 2]
    cloud_layer = add_edge_fade_mask(cloud_layer, cloudy_segs, seg_count=seg_count)
    for _ in range(frame_count):
        frame = track.copy()
        step_winners = []
        for idx in range(0, lane_count):
            car = get_car(players[idx].attributes.get("car_index", players[idx].id % cars_count))
            car = car.rotate(270, expand=True)
            part_before = int(seg_count * positions[idx] // max_x)
            positions[idx] = positions[idx] + base_speeds[idx]
            x = int(positions[idx])
            part_after = int(seg_count * positions[idx] // max_x)
            if part_before != part_after or weather_factor[idx] < -1000.0:
                wheels = players[idx].attributes.get("wheels", 0)
                seg = -1 if part_after >= len(type_segs) else type_segs[part_after]
                min_w = 0
                max_w = 0
                if seg == 0:
                    min_w, max_w = (0.15, 0.2) if wheels == 0 else (0.0, 0.05) if wheels == 1 else (0.05, 0.2)
                elif seg == 1:
                    min_w, max_w = (0.05, 0.2) if wheels == 0 else (0.2, 0.8) if wheels == 1 else (0.0, 0.05)
                elif seg == 2:
                    min_w, max_w = (0.05, 0.2) if wheels == 0 else (0.0, 0.05) if wheels == 1 else (0.3, 0.6)
                weather_factor[idx] = random.uniform(min_w, max_w)
                speed_factors[idx] += part_after * random.uniform(0.0, 0.02)
                base_speeds[idx] = (max_x + car_w) * (speed_factors[idx] + weather_factor[idx]) / frame_count
            # Вертикаль: центрируем машину в своей полосе
            y = idx * 70 + (70 - car_h) // 2
            draw_car_with_shadow(car, frame, x, y)
            if positions[idx] >= max_x - finish_block_size * 2:
                draw_car_with_shadow(car, frame, 0, y)
                if idx not in winners:
                    step_winners.append((idx, positions[idx]))

        # Накладываем слои
        for rainy_seg in [idx for idx, t in enumerate(type_segs) if t == 1]:
            seg, seg_x = get_frame_segment(frame, rainy_seg, seg_count)
            seg = make_rain_layer(seg)
            frame.paste(seg, (seg_x, 0))

        frame = Image.alpha_composite(frame, cloud_layer)

        [winners.append(t[0]) for t in sorted(step_winners, key=lambda x: x[1], reverse=True)]
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
    clip = ImageSequenceClip(np_frames, fps=60)
    clip.write_videofile(
        f"race_{chat_id}.mp4",
        codec="libx264",
        ffmpeg_params=["-movflags", "faststart"],
        audio=False
    )
    return winners


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


def get_frame_segment(frame, segment_index, seg_count):
    w, h = frame.size
    seg_w = w // seg_count
    seg_x = seg_w * segment_index
    return frame.crop((seg_x, 0, seg_x + seg_w, h)), seg_x


if __name__ == "__main__":
    # Пример: 5 полос
    class Player:
        def __init__(self, title, wheels: int):
            self.title = title
            self.id = random.randint(1, 24)
            self.attributes = dict()
            self.attributes["wheels"] = wheels
            self.attributes["car_index"] = self.id


    players = [Player("Alice", 0), Player("Bob", 0), Player("Charlie", 0),
               Player("Dave", 1), Player("Eve", 1), Player("Frank", 1),
               Player("Grace", 2), Player("Helen", 2), Player("Ivan", 2)]
    winners = create_race_gif(players, 2)
    print(winners)
    # track = draw_start_race_track(players, bg_color=(120, 120, 120))
    # # rain = make_rain_layer(track)
    # # track = Image.alpha_composite(track, rain)
    # track.save("race_track2.png")
    # track.show()
