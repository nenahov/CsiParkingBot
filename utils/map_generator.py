import random

from PIL import Image, ImageDraw, ImageFont

from models.driver import Driver
from models.parking_spot import ParkingSpot, SpotStatus

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

garbage_truck_frames = [(-1000, -1000, 0), (-1000, -1000, 0), (-1000, -1000, 0), (-1000, -1000, 0), (-1000, -1000, 0),
                        (1030, 610, 45), (1020, 510, 10),
                        (980, 480, 45), (840, 470, 90), (580, 470, 90), (200, 470, 90),
                        (110, 450, 45), (117, 370, -3), (125, 180, -20),
                        (265, 170, 268), (130, 175, 270), (145, 170, 270), (130, 170, 270), (135, 170, 270),
                        (270, 180, 250), (475, 220, 270), (830, 218, 270), (980, 215, 240),
                        (1030, 245, 184), (1042, 460, 180), (1042, 610, 200)]

dx = -28
dy = -16
d_width = -1

try:
    font = ImageFont.truetype("arial.ttf", 12)
except:
    font = ImageFont.load_default()


def generate_parking_map(parking_spots,
                         reservations_data,
                         driver: Driver,
                         use_spot_status: bool = True,
                         frame_index: int = None):
    # img = Image.new('RGB', (800, 600), (255, 255, 255))
    img = Image.open("./pics/parking.png")
    cars = Image.open("./pics/cars.png").convert("RGBA")
    # cars2 = Image.open("./pics/cars2.png").convert("RGBA")
    cars3 = Image.open("./pics/cars3.png").convert("RGBA")

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))

    try:
        font = ImageFont.truetype("arial.ttf", 8)
    except:
        font = ImageFont.load_default()

    # Отрисовка всех мест с учетом статусов
    for spot in parking_spots:
        status = get_status(driver, reservations_data, spot, use_spot_status)

        # Создаем паттерн с диагональными полосами
        pattern = create_diagonal_pattern(spot.width + d_width, spot.height,
                                          stripe_width=4,
                                          color2=COLORS[status],
                                          color1=(255, 255, 255, 0))

        # Вставляем паттерн в прямоугольник
        x = dx + spot.x
        y = dy + spot.y
        car_x = -1000
        car_y = -1000
        car_rotate = 0
        if 18 <= spot.id <= 34:
            x = 171 + int((spot.id - 18) * 51)
            y = 371
            car_x = x + 3
            car_y = y + 3
            car_rotate = 180
        elif 35 <= spot.id <= 51:
            x = 171 + int((spot.id - 35) * 51)
            y = 270
            car_x = x + 3
            car_y = y + 14
            car_rotate = 0
        elif spot.id == 74:
            x = 17
            y = 220
            car_x = x + 3
            car_y = y + 5
            car_rotate = -90
        overlay.paste(pattern, (x, y))

        if (use_spot_status
                and spot.current_driver_id is not None
                and spot.status is not None
                and spot.status in (SpotStatus.OCCUPIED, SpotStatus.OCCUPIED_WITHOUT_DEMAND)):
            car_index = spot.current_driver_id
            car_image = extract_sprite(cars3, (50 * (car_index % 12), 100 * (car_index % 2),
                                               50 * (1 + (car_index % 12)), 100 * (1 + (car_index % 2))))
            scale = 0.8
            if scale != 1:
                new_size = (int(car_image.width * scale), int(car_image.height * scale))
                car_image = car_image.resize(new_size)
            car_image = car_image.rotate(car_rotate + random.randint(-5, 5), expand=True)
            overlay.paste(car_image, (car_x, car_y), mask=car_image)

        # Добавляем текст
        # text = f"Место {spot.id}\n\n{reserved_by or 'Свободно'}"
        # draw.text((dx + spot.x + 2, dy + spot.y + 5), text, font=font, fill=COLORS['text'])

    if frame_index:
        # Рисуем мусорку
        garbage_truck = extract_sprite(cars, (0, 130, 55, 255))
        scale = 0.8
        if scale != 1:
            new_size = (int(garbage_truck.width * scale), int(garbage_truck.height * scale))
            garbage_truck = garbage_truck.resize(new_size)
        frame = garbage_truck_frames[frame_index % len(garbage_truck_frames)]
        garbage_truck = garbage_truck.rotate(frame[2], expand=True)
        overlay.paste(garbage_truck, (frame[0] + random.randint(-5, 5), frame[1] + random.randint(0, 5)),
                      mask=garbage_truck)

    img = Image.alpha_composite(img, overlay)

    return img


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


def extract_sprite(sprite_sheet, sprite_rect):
    """
    Извлекает спрайт из спрайт-листа.

    :param sprite_sheet: Изображение со спрайт-листом (PIL Image)
    :param sprite_rect: Кортеж (left, top, right, bottom), задающий область спрайта
    :return: Извлечённое изображение спрайта
    """
    return sprite_sheet.crop(sprite_rect)
