import io
import logging
import random
from collections import Counter
from functools import lru_cache

from PIL import Image, ImageDraw, ImageOps, ImageFilter, ImageFont
from imageio_ffmpeg import write_frames

from utils.game_race_utils import GameState
from utils.race_simulation import (
    NITRO_PULSE_FRAMES, RaceAction, RaceSimulationResult, resolve_race_simulation,
)
from utils.weather_generator import make_sun_glare_layer, get_clouds_layer, add_edge_fade_mask, make_rain_layer

logger = logging.getLogger(__name__)

cars3 = Image.open("./pics/cars3.png").convert("RGBA")
avatar_cars = Image.open("./pics/cars4.png").convert("RGBA")
cars_count = 60
extra_cars_count = 60
avatar_car_columns = 12
avatar_car_rows = 5
avatar_car_left = 3
avatar_car_top = 17
avatar_car_width = 116
avatar_car_height = 213
regular_font = ImageFont.truetype("ariali.ttf", 40)
car_w, car_h = (100, 50)
finish_block_size = 5
RACE_LANE_HEIGHT = 70
RACE_TRACK_LENGTH = 1800
RACE_HUD_HEIGHT = 76
RACE_FOOTER_HEIGHT = 34
RACE_START_FRAMES = 45
RACE_FINISH_FRAMES = 48
RACE_FPS = 60
NITRO_GLOW_FRAMES = 20
PODIUM_COLORS = ((244, 194, 67), (200, 213, 224), (205, 137, 83))


def _race_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Загрузить читаемый шрифт для кириллицы на номерках и табло."""
    return ImageFont.truetype("arialbd.ttf" if bold else "arial.ttf", size)


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


def generate_avatar_gallery_image(
        start_index: int,
        cars_count_for_driver: int,
        selected_index: int | None = None,
) -> io.BytesIO:
    """Рисует контактный лист 3×4 для выбора аватара."""
    columns, rows = 3, 4
    cell_width, cell_height = 180, 140
    gap, padding = 12, 18
    width = padding * 2 + columns * cell_width + (columns - 1) * gap
    height = padding * 2 + rows * cell_height + (rows - 1) * gap
    canvas = Image.new("RGB", (width, height), "#101923")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()

    for offset in range(columns * rows):
        car_index = start_index + offset
        if car_index >= cars_count_for_driver:
            break

        col, row = offset % columns, offset // columns
        x = padding + col * (cell_width + gap)
        y = padding + row * (cell_height + gap)
        is_selected = car_index == selected_index
        card_color = "#263b48" if is_selected else "#1a2934"
        border_color = "#f6c453" if is_selected else "#344957"
        draw.rounded_rectangle(
            (x, y, x + cell_width, y + cell_height),
            radius=14,
            fill=card_color,
            outline=border_color,
            width=3 if is_selected else 1,
        )

        car = get_avatar_car(car_index).convert("RGBA")
        car.thumbnail((cell_width - 28, cell_height - 44), Image.Resampling.LANCZOS)
        car_x = x + (cell_width - car.width) // 2
        car_y = y + 8 + (cell_height - 44 - car.height) // 2
        canvas.paste(car, (car_x, car_y), car)
        draw.text(
            (x + 10, y + cell_height - 26),
            f"#{car_index + 1}",
            font=font,
            fill="#f4f7f9",
        )

    bio = io.BytesIO()
    canvas.save(bio, format="PNG")
    bio.seek(0)
    return bio


def generate_avatar_preview_image(current_index: int) -> io.BytesIO:
    """Рисует крупное превью одной машинки."""
    width, height = 640, 360
    canvas = Image.new("RGB", (width, height), "#101923")
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        (12, 12, width - 12, height - 12),
        radius=24,
        fill="#1a2934",
        outline="#344957",
        width=2,
    )

    car = get_avatar_car(current_index).convert("RGBA")
    car.thumbnail((width - 120, height - 100), Image.Resampling.LANCZOS)
    canvas.paste(car, ((width - car.width) // 2, (height - car.height) // 2), car)
    draw.text(
        (28, height - 42),
        f"#{current_index + 1}",
        font=ImageFont.load_default(),
        fill="#f4f7f9",
    )

    bio = io.BytesIO()
    canvas.save(bio, format="PNG")
    bio.seek(0)
    return bio


def get_car(current_index):
    """Вырезать спрайт выбранной гоночной машины из общего листа."""
    current_index = current_index
    return extract_sprite(cars3, (50 * (current_index % 12), 100 * (current_index // 12),
                                  50 * (1 + (current_index % 12)), 100 * (1 + (current_index // 12))))


def get_avatar_car(current_index: int) -> Image.Image:
    """Извлекает машинку из cars4.png по сетке 12×5 с заданными отступами."""
    column = current_index % avatar_car_columns
    row = current_index // avatar_car_columns
    left = avatar_car_left + column * avatar_car_width
    right = left + avatar_car_width
    top = avatar_car_top + row * avatar_car_height
    bottom = top + avatar_car_height
    return avatar_cars.crop((left, top, right, bottom))


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
    """Нарисовать мультяшную прямую трассу сверху, по полосе на участника.

    Размеры и координаты сохраняются: позиции симуляции измеряются в пикселях
    от левого края, а ширина машины остаётся равной ``car_w``.
    """
    img_height = len(players) * lane_height
    img = Image.new('RGB', (track_length, img_height), (53, 119, 72))
    draw = ImageDraw.Draw(img)
    # Чередующиеся полосы асфальта придают трассе объём, не мешая спрайтам.
    for i in range(len(players)):
        top = i * lane_height
        draw.rectangle((0, top + 7, track_length, top + lane_height - 7),
                       fill=(55, 65, 77) if i % 2 == 0 else (61, 72, 84))
        draw.line((0, top + 8, track_length, top + 8), fill=(91, 102, 110), width=2)
        draw.line((0, top + lane_height - 8, track_length, top + lane_height - 8),
                  fill=(38, 49, 58), width=2)
        # Неброские метки расстояния сохраняют ощущение движения.
        for x in range(275, track_length - 30, 300):
            draw.line((x, top + 29, x + 14, top + 29), fill=(79, 92, 103), width=2)

    # Штриховые разделители и красно-белые бордюры.
    for i in range(1, len(players)):
        y = i * lane_height
        for x in range(0, track_length, 64):
            draw.line((x, y, min(x + 34, track_length), y),
                      fill=(204, 213, 198), width=2)
    for x in range(0, track_length, 40):
        color = (232, 77, 65) if x // 40 % 2 == 0 else (246, 239, 218)
        draw.rectangle((x, 0, min(x + 39, track_length), 8), fill=color)
        draw.rectangle((x, img_height - 8, min(x + 39, track_length), img_height),
                       fill=color)

    # Старт и клетчатый финиш в точках, соответствующих длине машины.
    draw.rectangle((103, 8, 108, img_height - 9), fill=(242, 232, 193))
    finish_x = track_length - 20
    for row in range(0, img_height, 10):
        for col in range(2):
            color = (243, 240, 225) if row // 10 % 2 == col else (28, 37, 45)
            draw.rectangle((finish_x + col * 10, row, finish_x + col * 10 + 9,
                            min(row + 9, img_height - 1)), fill=color)

    # Подписи у старта видны в начале; затем их заменяют маркеры на машинах.
    label_font = _race_font(min(19, max(12, lane_height // 3)), bold=True)
    for idx, player in enumerate(players):
        label = f"{idx + 1} · {player.title}"
        draw.text((122, idx * lane_height + (lane_height - label_font.size) // 2),
                  label[:28], font=label_font, fill=(165, 180, 185),
                  stroke_width=1, stroke_fill=(29, 40, 50))

    return img


def draw_start_race_track(players, lane_height=70, track_length=800,
                          bg_color=(50, 50, 50)):
    """Нарисовать прямую трассу с машинами на стартовых позициях."""
    img = draw_race_track(players, lane_height=lane_height,
                          track_length=track_length,
                          bg_color=bg_color)
    for idx, player in enumerate(players):
        y = idx * lane_height + (lane_height - car_h) // 2
        car = get_car(player.attributes.get("car_index", player.id % cars_count))
        car = car.rotate(270, expand=True)
        draw_car_with_shadow(car, img, 0, y)
    return img


def create_race_gif(
        game_state: GameState,
        players,
        chat_id: int | str,
        output_path='race.gif',
        frame_count=50,
        duration=100,
        simulation_result: RaceSimulationResult | None = None,
        actions: dict[int, RaceAction] | None = None,
):
    """Создать MP4 и, если указан путь, GIF по результату одной симуляции.

    ``output_path=None`` не собирает GIF в памяти (режим бота). Стартовая
    заставка и финишный стоп-кадр не сдвигают такты симуляции и порядок мест.
    """
    if frame_count < 1:
        raise ValueError("В гонке должен быть хотя бы один кадр")
    track = draw_race_track(players=players,
                            lane_height=RACE_LANE_HEIGHT,
                            track_length=RACE_TRACK_LENGTH).convert('RGBA')
    max_x = float(track.width - car_w)
    wheels = [
        game_state.wheels.get(
            str(player.id),
            game_state.wheels.get(player.id, player.attributes.get("wheels", 0)),
        )
        for player in players
    ]
    if simulation_result is None:
        simulation_result = resolve_race_simulation(
            players=players,
            wheels=wheels,
            weather_forecast=game_state.weather,
            actions=actions,
            seed=random.randrange(2 ** 31),
            frame_count=frame_count,
            track_distance=max_x,
            car_width=car_w,
        )
    # Погода затемняет асфальт, но не перекрывает машины и номерные знаки.
    weather = simulation_result.weather_segments
    logger.info("Race weather segments: %s", weather)
    if any(kind == 2 for kind in weather):
        sunny = [idx for idx, kind in enumerate(weather) if kind == 2]
        glare = make_sun_glare_layer(track.size, max_alpha=45)
        track = Image.alpha_composite(
            track, add_edge_fade_mask(glare, sunny, seg_count=3))
    if any(kind != 2 for kind in weather):
        cloudy = [idx for idx, kind in enumerate(weather) if kind != 2]
        clouds = add_edge_fade_mask(
            get_clouds_layer(track, seed=simulation_result.seed),
            cloudy, seg_count=3)
        track = Image.alpha_composite(track, clouds)
    for rainy in (idx for idx, kind in enumerate(weather) if kind == 1):
        segment, seg_x = get_frame_segment(track, rainy, 3)
        track.paste(make_rain_layer(segment, lightning_chance=0), (seg_x, 0))

    cars = [
        get_car(player.attributes.get("car_index", player.id % cars_count))
        .rotate(270, expand=True)
        for player in players
    ]
    shadows = [_make_car_shadow(car) for car in cars]
    height = track.height + RACE_HUD_HEIGHT + RACE_FOOTER_HEIGHT
    video = write_frames(
        f"race_{chat_id}.mp4", (track.width, height),
        fps=RACE_FPS, codec="libx264", macro_block_size=1,
        output_params=["-movflags", "faststart"],
    )
    frames = [] if output_path is not None else None
    intro = min(RACE_START_FRAMES, frame_count // 8)
    outro = min(RACE_FINISH_FRAMES, frame_count // 8)
    video.send(None)
    try:
        for video_frame in range(intro + frame_count + outro):
            frame_index = min(max(video_frame - intro, 0), frame_count - 1)
            phase = ("start" if video_frame < intro else
                     "finish" if video_frame >= intro + frame_count else "race")
            frame = _render_race_frame(
                track, cars, shadows, players, simulation_result,
                frame_index, phase=phase, intro_frame=video_frame,
            )
            rgb = frame.convert("RGB")
            video.send(rgb.tobytes())
            if frames is not None:
                frames.append(rgb.convert("P", palette=Image.Palette.ADAPTIVE))
    finally:
        video.close()
    if frames:
        frames[0].save(output_path, save_all=True, append_images=frames[1:],
                       duration=max(duration, round(1000 / RACE_FPS)), loop=0)
    return simulation_result.winners


def _make_car_shadow(car_image: Image.Image) -> Image.Image:
    """Один раз подготовить полупрозрачную мягкую тень спрайта."""
    shadow = Image.new("RGBA", car_image.size, (0, 0, 0, 0))
    shadow.putalpha(car_image.getchannel("A").point(lambda alpha: int(alpha * .55)))
    return shadow.filter(ImageFilter.GaussianBlur(5))


def _draw_car_number(frame: Image.Image, x: int, y: int,
                     size: tuple[int, int], number: int) -> None:
    """Написать номер по центру корпуса без кружка и фоновой плашки."""
    draw = ImageDraw.Draw(frame)
    draw.text((x + size[0] // 2, y + size[1] // 2), str(number),
              font=_race_font(22, bold=True), fill=(255, 255, 248),
              stroke_width=2, stroke_fill=(15, 31, 43), anchor="mm")


def _draw_race_hud(frame: Image.Image, players, simulation_result,
                   frame_index: int, phase: str, intro_frame: int) -> None:
    """Показать тройку лидеров и короткие заставки без раскрытия переводов нитро."""
    draw = ImageDraw.Draw(frame)
    width, height = frame.size
    draw.rectangle((0, 0, width, RACE_HUD_HEIGHT), fill=(23, 38, 52))
    draw.rectangle((0, height - RACE_FOOTER_HEIGHT, width, height),
                   fill=(23, 38, 52))
    draw.line((0, RACE_HUD_HEIGHT - 2, width, RACE_HUD_HEIGHT - 2),
              fill=(245, 194, 83), width=3)
    ordered = _race_order(simulation_result, len(players), frame_index)
    if phase == "finish":
        ordered = simulation_result.winners
    draw.text((22, 12), "ГОНКА  •  НИТРО", font=_race_font(25, bold=True),
              fill=(250, 218, 116))
    for place, idx in enumerate(ordered[:3]):
        left = 340 + place * 460
        medal_color = PODIUM_COLORS[place]
        draw.rounded_rectangle((left, 12, left + 442, 63), radius=13,
                               fill=(41, 62, 77), outline=medal_color, width=2)
        draw.ellipse((left + 10, 20, left + 46, 56),
                     fill=medal_color, outline=(255, 245, 211), width=2)
        draw.text((left + 28, 38), str(idx + 1), font=_race_font(19, bold=True),
                  fill=(20, 39, 53), anchor="mm")
        draw.text((left + 59, 24), players[idx].title[:19],
                  font=_race_font(23, bold=True), fill=(244, 246, 239))
    progress = max(0, min(1, (frame_index + 1) / max(1, simulation_result.frame_count)))
    draw.rounded_rectangle((26, height - 23, width - 26, height - 12),
                           radius=5, fill=(66, 89, 99))
    draw.rounded_rectangle((26, height - 23,
                            26 + int((width - 52) * progress), height - 12),
                           radius=5, fill=(54, 186, 244))
    if phase == "start":
        number = 3 - min(2, intro_frame // max(1, RACE_START_FRAMES // 3))
        _draw_race_banner(frame, f"СТАРТ ЧЕРЕЗ {number}")
    elif phase == "finish":
        winner = players[simulation_result.winners[0]].title
        _draw_race_banner(frame, f"ФИНИШ!  # {simulation_result.winners[0] + 1}  {winner[:15]}")


def _race_order(simulation_result, player_count: int, frame_index: int) -> list[int]:
    """Упорядочить табло: финишировавшие раньше тех, кто ещё едет."""
    # Финишировавшие навсегда остаются в порядке пересечения линии: дальнейшая
    # экстраполяция position_at не должна менять лидера на табло.
    finish_frames = getattr(simulation_result, "finish_frames", None)
    finished = (
        [idx for idx in simulation_result.winners
         if finish_frames[idx] is not None and finish_frames[idx] <= frame_index]
        if finish_frames else []
    )
    remaining = sorted(
        (idx for idx in range(player_count) if idx not in finished),
        key=lambda idx: (-simulation_result.position_at(idx, frame_index), idx),
    )
    return finished + remaining


def _draw_race_banner(frame: Image.Image, text: str) -> None:
    """Наложить полупрозрачную карточку старта или победителя."""
    layer = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    cx, cy = frame.width // 2, frame.height // 2
    draw.rounded_rectangle((cx - 330, cy - 48, cx + 330, cy + 48),
                           radius=24, fill=(21, 39, 53, 224),
                           outline=(250, 203, 83, 255), width=4)
    draw.text((cx, cy), text, font=_race_font(34, bold=True),
              fill=(255, 250, 226), anchor="mm")
    frame.alpha_composite(layer)


def _display_position(simulation_result: RaceSimulationResult, racer: int,
                      frame_index: int) -> float:
    """Сгладить лишь экранную позицию; физику и порядок финиша не менять.

    Симметричный пятикадровый фильтр убирает визуальный рывок в начале и
    конце импульса. После пересечения финиша спрайт больше не едет вперёд.
    """
    finish_frames = getattr(simulation_result, "finish_frames", None)
    last_frame = simulation_result.frame_count - 1
    if finish_frames and finish_frames[racer] is not None:
        last_frame = min(last_frame, finish_frames[racer])
    weights = (1, 2, 3, 2, 1)
    return sum(
        weight * simulation_result.position_at(
            racer, min(last_frame, max(0, frame_index + offset)))
        for weight, offset in zip(weights, (-2, -1, 0, 1, 2))
    ) / sum(weights)


def _nitro_intensity(pulses: tuple[int, ...], frame_index: int) -> float:
    """Продлить свечение после физического импульса и плавно погасить его."""
    ages = (frame_index - start for start in pulses
            if start <= frame_index < start + NITRO_GLOW_FRAMES)
    age = min(ages, default=None)
    if age is None:
        return 0.0
    if age < NITRO_PULSE_FRAMES:
        return 1.0
    return (NITRO_GLOW_FRAMES - age) / (NITRO_GLOW_FRAMES - NITRO_PULSE_FRAMES)


def _render_race_frame(track, cars, shadows, players, simulation_result,
                       frame_index: int, phase: str = "race",
                       intro_frame: int = 0) -> Image.Image:
    """Собрать один кадр; координаты берутся только из готовой симуляции."""
    frame = Image.new("RGBA", (track.width,
                               track.height + RACE_HUD_HEIGHT + RACE_FOOTER_HEIGHT),
                      (23, 38, 52, 255))
    frame.alpha_composite(track, (0, RACE_HUD_HEIGHT))
    for idx, (car, shadow) in enumerate(zip(cars, shadows)):
        x = max(0, min(track.width - car.width,
                       int(_display_position(simulation_result, idx, frame_index))))
        y = RACE_HUD_HEIGHT + idx * RACE_LANE_HEIGHT + (RACE_LANE_HEIGHT - car.height) // 2
        # Физика импульса по-прежнему длится пять тактов; след виден дольше.
        if simulation_result.nitro_pulses:
            intensity = _nitro_intensity(
                simulation_result.nitro_pulses[idx], frame_index)
            if intensity:
                draw_nitro_flame(frame, x, y, car.size, intensity=intensity)
        frame.alpha_composite(shadow, (x + 4, y + 4))
        frame.alpha_composite(car, (x, y))
        _draw_car_number(frame, x, y, car.size, idx + 1)
    _draw_race_hud(frame, players, simulation_result, frame_index, phase, intro_frame)
    return frame


@lru_cache(maxsize=64)
def _nitro_glow_sprite(size: tuple[int, int], level: int) -> Image.Image:
    """Заготовить мягкое свечение под машиной для эффекта нитро."""
    width, height = size
    pad_x, pad_y = 20, 12
    canvas_size = (width + 2 * pad_x, height + 2 * pad_y)

    outer_mask = Image.new("L", canvas_size, 0)
    brush = ImageDraw.Draw(outer_mask)
    brush.ellipse((pad_x - 2, pad_y - 1, pad_x + width + 2,
                   pad_y + height + 1), fill=115)
    outer = Image.new("RGBA", canvas_size, (12, 94, 255, 0))
    outer.putalpha(outer_mask.filter(ImageFilter.GaussianBlur(9)))

    inner_mask = Image.new("L", canvas_size, 0)
    brush = ImageDraw.Draw(inner_mask)
    brush.ellipse((pad_x + 2, pad_y + 7, pad_x + width - 9,
                   pad_y + height - 7), fill=105)
    # Свет у двух задних колёс остаётся частью общего ореола, а не следом.
    for center_y in (pad_y + 12, pad_y + height - 12):
        brush.ellipse((pad_x - 3, center_y - 9, pad_x + 25, center_y + 9),
                      fill=145)
    inner = Image.new("RGBA", canvas_size, (62, 194, 255, 0))
    inner.putalpha(inner_mask.filter(ImageFilter.GaussianBlur(5)))
    outer.alpha_composite(inner)
    outer.putalpha(outer.getchannel("A").point(lambda alpha: alpha * level // 16))
    return outer


@lru_cache(maxsize=64)
def _nitro_jet_sprite(size: tuple[int, int], level: int) -> Image.Image:
    """Заготовить короткую объёмную струю, выходящую прямо из заднего бампера."""
    _, height = size
    pad_left, pad_top = 42, 12
    canvas_size = (pad_left + 18, height + pad_top * 2)
    center_y = canvas_size[1] // 2

    # Размытый внешний ореол делает струю мягкой, но её форма остаётся
    # компактной и не превращается в горизонтальную полосу на трассе.
    glow_mask = Image.new("L", canvas_size, 0)
    glow_draw = ImageDraw.Draw(glow_mask)
    glow_draw.polygon(
        ((pad_left + 10, center_y - 5), (pad_left - 15, center_y - 14),
         (2, center_y), (pad_left - 15, center_y + 14),
         (pad_left + 10, center_y + 5)),
        fill=120,
    )
    glow = Image.new("RGBA", canvas_size, (0, 126, 255, 0))
    glow.putalpha(glow_mask.filter(ImageFilter.GaussianBlur(7)))

    flame = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    flame_draw = ImageDraw.Draw(flame)
    flame_draw.polygon(
        ((pad_left + 11, center_y - 4), (pad_left - 13, center_y - 9),
         (4, center_y), (pad_left - 13, center_y + 9),
         (pad_left + 11, center_y + 4)),
        fill=(41, 190, 255, 205),
    )
    flame_draw.polygon(
        ((pad_left + 12, center_y - 2), (pad_left - 8, center_y - 4),
         (8, center_y), (pad_left - 8, center_y + 4),
         (pad_left + 12, center_y + 2)),
        fill=(205, 247, 255, 240),
    )
    glow.alpha_composite(flame)
    glow.putalpha(glow.getchannel("A").point(lambda alpha: alpha * level // 16))
    return glow


def draw_nitro_flame(frame, x, y, size, intensity=1.0):
    """Нарисовать мягкий ореол и короткую красивую струю из кормы."""
    if intensity <= 0:
        return
    level = max(1, min(16, round(intensity * 16)))
    glow = _nitro_glow_sprite(tuple(size), level)
    frame.alpha_composite(glow, (x - 20, y - 12))
    jet = _nitro_jet_sprite(tuple(size), level)
    # Машина накладывается после эффекта, поэтому начало струи естественно
    # прячется под задним бампером.
    frame.alpha_composite(jet, (x - 42, y - 12))


def get_weather_for_segments(seg_count, game_state: GameState, players):
    """Выбрать погоду участков для старого самостоятельного рендера."""
    result = []
    # цикл от 1 до 2 включительно
    for i in range(1, 3):
        # получаем погоду на i сегменте и добавляем в результат
        result.append(random.choices([0, 1, 2], weights=game_state.weather.get(str(i)), k=1)[0])

    # Для последнего сегмента выберем подходящую погоду для наименее популярных колес(шин)
    lst = [p.attributes.get("wheels", 0) for p in players]
    # Считаем частоту всех трех типов, включая отсутствующие в заезде.
    counts = Counter(lst)
    counts.update({0: 0, 1: 0, 2: 0})
    # Находим минимальную частоту
    min_freq = min(counts.values())
    # Собираем все числа с этой частотой
    least_common = [num for num, freq in counts.items() if freq == min_freq]
    # Выбираем случайно одно из них
    result.append(random.choice(least_common))

    return result


def draw_car_with_shadow(
        car_image,
        frame,
        car_x,
        car_y,
        shadow_dx=5,
        shadow_dy=5,
        blur_radius=10
):
    """Наложить спрайт машины и мягкую тень на кадр трассы."""
    # Создаем тень
    shadow = Image.new("RGBA", car_image.size, (0, 0, 0, 0))
    shadow.putalpha(car_image.split()[3])
    shadow = ImageOps.colorize(shadow.convert("L"), black="black", white="black")
    shadow.putalpha(car_image.split()[3])
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur_radius))

    # Смещаем тень относительно машины
    shadow_position = (car_x + shadow_dx, car_y + shadow_dy)

    # Накладываем тень
    frame.paste(shadow, shadow_position, mask=car_image)
    frame.paste(car_image, (car_x, car_y), car_image)


def get_frame_segment(frame, segment_index, seg_count):
    """Вырезать участок кадра для локального погодного эффекта."""
    w, h = frame.size
    seg_w = w // seg_count
    seg_x = seg_w * segment_index
    return frame.crop((seg_x, 0, seg_x + seg_w, h)), seg_x


def main() -> RaceSimulationResult:
    """Эмулировать полноценную гонку с нитро и записать ``race_demo.mp4``.

    Запуск из корня проекта: ``python -m utils.cars_generator``.
    Фиксированный seed сохраняет те же запасы нитро, позиции и порядок мест.
    """

    class DemoPlayer:
        """Минимальный водитель для автономного просмотра без базы и Telegram."""

        def __init__(self, player_id: int, title: str, wheels: int,
                     car_index: int):
            """Запомнить номер, имя, шины и существующий спрайт машины."""
            self.id = player_id
            self.title = title
            self.attributes = {"wheels": wheels, "car_index": car_index}

    names = ("Алиса", "Борис", "Вера", "Глеб", "Даша",
             "Егор", "Женя", "Зоя", "Игорь")
    car_indices = (40, 24, 12, 19, 25, 31, 36, 48, 50)
    players = [
        DemoPlayer(i + 1, name, i % 3, car_indices[i])
        for i, name in enumerate(names)
    ]
    game_state = GameState({"1": [5, 3, 2], "2": [2, 3, 5]})
    for player in players:
        game_state.add_player(player)
        game_state.wheels[str(player.id)] = player.attributes["wheels"]

    # Каждый выбирает три разные пары «украсть → подарить», три защиты
    # и момент расхода нитро. Защиты намеренно разные, чтобы итоговые
    # запасы отличались и в видео были видны разные серии вспышек.
    guards = (
        (3, 4, 5), (0, 2, 4), (0, 5, 6),
        (1, 4, 8), (0, 3, 7), (0, 6, 8),
        (2, 3, 7), (1, 5, 8), (0, 2, 6),
    )
    for i, player in enumerate(players):
        game_state.actions[player.id] = RaceAction(
            kind="nitro",
            transfers=tuple(
                ((i + offset) % len(players) + 1,
                 (i + offset + 3) % len(players) + 1)
                for offset in (1, 2, 3)
            ),
            guards=tuple(index + 1 for index in guards[i]),
            plan=("early", "steady", "late")[i % 3],
        )
    seed = 20261026
    frame_count = 400
    simulation = resolve_race_simulation(
        players=players,
        wheels=[player.attributes["wheels"] for player in players],
        weather_forecast=game_state.weather,
        actions=game_state.resolve_actions(),
        seed=seed,
        frame_count=frame_count,
        track_distance=RACE_TRACK_LENGTH - car_w,
        car_width=car_w,
    )
    print("Нитро перед стартом:")
    for i, player in enumerate(players):
        print(f"  #{i + 1} {player.title}: {simulation.nitro[i]} "
              f"(план: {game_state.actions[player.id].plan})")
    create_race_gif(
        game_state, players, chat_id="demo", output_path=None,
        frame_count=frame_count, simulation_result=simulation,
    )
    print("Финиш:", " -> ".join(
        f"#{i + 1} {players[i].title}" for i in simulation.winners
    ))
    print("Видео: race_demo.mp4")
    return simulation


if __name__ == "__main__":
    main()
