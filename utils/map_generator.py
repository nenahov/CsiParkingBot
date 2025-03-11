from PIL import Image, ImageDraw, ImageFont

# Цвета для разных статусов
COLORS = {
    'free': (184, 255, 184),  # Светло-зеленый
    'my_reserved': (255, 165, 0),  # Оранжевый
    'reserved': (255, 99, 71),  # Красный
    'text': (0, 0, 0)  # Черный
}

try:
    font = ImageFont.truetype("arial.ttf", 12)
except:
    font = ImageFont.load_default()


def generate_parking_map(parking_spots, reservations_data, current_user_id):
    # img = Image.new('RGB', (800, 600), (255, 255, 255))
    img = Image.open("./pics/parking.png")
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("arial.ttf", 8)
    except:
        font = ImageFont.load_default()

    # Отрисовка всех мест с учетом статусов
    for spot in parking_spots:
        status = 'free'
        reserved_by = None

        # Проверка резерваций для текущего места
        for res in reservations_data.get(spot.id, []):
            if res.driver.chat_id == current_user_id:
                status = 'my_reserved'
                reserved_by = res.driver.username or f"user_{res.driver.chat_id}"
                break
            else:
                status = 'reserved'
                reserved_by = res.driver.username or f"user_{res.driver.chat_id}"

        # Рисуем прямоугольник
        draw.rectangle(
            [(spot.x, spot.y), (spot.x + spot.width, spot.y + spot.height)],
            fill=COLORS[status],
            outline=COLORS[status]
        )

        # Добавляем текст
        text = f"Место {spot.id}\n\n{reserved_by or 'Свободно'}"
        draw.text((spot.x + 2, spot.y + 5), text, font=font, fill=COLORS['text'])

    return img
