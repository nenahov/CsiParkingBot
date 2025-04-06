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
    str(SpotStatus.OCCUPIED): (255, 20, 20, 200),  # Красный
    str(SpotStatus.OCCUPIED_WITHOUT_DEMAND): (255, 20, 20, 250),  # Красный

    str(SpotStatus.HIDDEN) + "_me": (0, 0, 0, 250),  # Светло-зеленый
    str(SpotStatus.FREE) + "_me": (100, 255, 100, 250),  # Светло-зеленый
    str(SpotStatus.OCCUPIED) + "_me": (255, 250, 0, 250),  # Желтый
    str(SpotStatus.OCCUPIED_WITHOUT_DEMAND) + "_me": (255, 200, 20, 250),  # Красный

    'text': (0, 0, 0)  # Черный
}

dx = -28
dy = -16
d_width = -1

try:
    font = ImageFont.truetype("arial.ttf", 12)
except:
    font = ImageFont.load_default()


def generate_parking_map(parking_spots, reservations_data, driver: Driver, use_spot_status: bool = True):
    # img = Image.new('RGB', (800, 600), (255, 255, 255))
    img = Image.open("./pics/parking.png")
    cars = Image.open("./pics/cars.png").convert("RGBA")
    cars2 = Image.open("./pics/cars2.png").convert("RGBA")

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

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
        if 18 <= spot.id <= 34:
            x = 171 + int((spot.id - 18) * 51)
            y = 371
        elif 35 <= spot.id <= 51:
            x = 171 + int((spot.id - 35) * 51)
            y = 270
        elif spot.id == 74:
            x = 17
            y = 220
        overlay.paste(pattern, (x, y))

        # Добавляем текст
        # text = f"Место {spot.id}\n\n{reserved_by or 'Свободно'}"
        # draw.text((dx + spot.x + 2, dy + spot.y + 5), text, font=font, fill=COLORS['text'])

    # Рисуем мусорку
    garbage_truck = extract_sprite(cars, (0, 130, 55, 255))
    garbage_truck = garbage_truck.rotate(270, expand=True)
    overlay.paste(garbage_truck, (135, 170), mask=garbage_truck)

    # car20 = extract_sprite(cars2, (63, 288, 93, 365))
    # overlay.paste(car20, (827 + dx, 195 + dy), mask=car20)

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
