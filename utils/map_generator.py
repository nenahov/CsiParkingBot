from PIL import Image, ImageDraw, ImageFont

# Цвета для разных статусов
COLORS = {
    'free': (100, 255, 100, 150),  # Светло-зеленый
    'my_reserved': (255, 250, 0, 97),  # Оранжевый
    'reserved': (255, 20, 20, 97),  # Красный
    'text': (0, 0, 0)  # Черный
}

dx = -39
dy = -18

try:
    font = ImageFont.truetype("arial.ttf", 12)
except:
    font = ImageFont.load_default()


def generate_parking_map(parking_spots, reservations_data, current_user_id):
    # img = Image.new('RGB', (800, 600), (255, 255, 255))
    img = Image.open("./pics/parking.png")

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

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
        # draw.rectangle(
        #     [(dx + spot.x, dy + spot.y), (dx + spot.x + spot.width, dy + spot.y + spot.height)],
        #     fill=COLORS[status],
        #     outline=COLORS[status]
        # )

        # Создаем паттерн с диагональными полосами
        pattern = create_diagonal_pattern(spot.width, spot.height,
                                          stripe_width=4,
                                          color2=COLORS[status],
                                          color1=(255, 255, 255, 0))

        # Вставляем паттерн в прямоугольник
        overlay.paste(pattern, (dx + spot.x, dy + spot.y))

        # Добавляем текст
        # text = f"Место {spot.id}\n\n{reserved_by or 'Свободно'}"
        # draw.text((dx + spot.x + 2, dy + spot.y + 5), text, font=font, fill=COLORS['text'])

    img = Image.alpha_composite(img, overlay)

    return img


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
