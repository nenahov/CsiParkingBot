"""Сборка подложки схемы. Бот вызывает ensure_parking_backdrop при старте и перед картой."""

import os
from datetime import date

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

from utils.parking_layout import (
    ASPHALT_RECTS,
    CANVAS_SIZE,
    DECOR,
    DUMPSTER_LABEL,
    QUEUE_SLOTS,
    RED_ROOF,
    SPOT_STALLS,
    WHITE_ROOF,
)

BACKDROP_PATH = os.path.join("pics", "parking_r.png")
KEY_PATH = os.path.join("pics", "parking_r.key")
ASSETS_DIR = os.path.join("pics", "assets")

ASPHALT = (54, 57, 62)
CURB = (118, 108, 96)
LINE = (242, 244, 246)
QUEUE_LINE = (232, 196, 48)
NUMBER = (255, 255, 255)

_assets = None


def _font(size, bold=False):
    names = ("comicbd.ttf", "comic.ttf", "arialbd.ttf") if bold else ("comic.ttf", "arial.ttf")
    for name in names:
        try:
            return ImageFont.truetype(f"C:/Windows/Fonts/{name}", size)
        except OSError:
            continue
    return ImageFont.load_default()


def backdrop_key(day, temp, weather):
    weather = weather or {}
    month = (day or date.today()).month
    if month in (12, 1, 2):
        season = "winter"
    elif month in (3, 4, 5):
        season = "spring"
    elif month in (6, 7, 8):
        season = "summer"
    else:
        season = "autumn"
    snow = weather.get("snow_count", 0) or (
            temp and "-" in str(temp) and weather.get("rain_drop_count", 0)
    )
    if season == "winter" or snow:
        return "winter"
    if weather.get("rain_drop_count", 0):
        return f"{season}-rain"
    return season


def _grass_color(key):
    season = key.split("-")[0]
    colors = {
        "summer": (176, 208, 112),
        "spring": (198, 222, 138),
        "autumn": (196, 164, 92),
        "winter": (228, 234, 236),
    }
    color = colors.get(season, colors["summer"])
    if key.endswith("-rain"):
        color = tuple(max(0, int(c * 0.72)) for c in color)
    return color


def _load_assets():
    global _assets
    if _assets is not None:
        return _assets
    _assets = {}
    if not os.path.isdir(ASSETS_DIR):
        return _assets
    for name in os.listdir(ASSETS_DIR):
        if name.lower().endswith(".png"):
            _assets[os.path.splitext(name)[0]] = Image.open(
                os.path.join(ASSETS_DIR, name)
            ).convert("RGBA")
    return _assets


def _tint(image, color, amount):
    image = image.convert("RGBA")
    tint = Image.new("RGBA", image.size, (*color, 0))
    tint.putalpha(image.getchannel("A").point(lambda p, a=amount: int(p * a)))
    return Image.alpha_composite(image, tint)


def _paste_bottom(base, sprite, cx, bottom, height=None, width=None):
    if sprite is None:
        return
    if width is not None:
        scale = width / sprite.width
    elif height:
        scale = height / sprite.height
    else:
        return
    size = (max(1, int(sprite.width * scale)), max(1, int(sprite.height * scale)))
    sprite = sprite.resize(size, Image.Resampling.LANCZOS)
    base.alpha_composite(sprite, (int(cx - sprite.width / 2), int(bottom - sprite.height)))


def _rounded(draw, box, radius, fill):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def _draw_fence(draw, x0, y0, x1, y1, vertical=False):
    post = (176, 112, 58)
    rail = (196, 132, 72)
    if vertical:
        y = y0
        while y < y1:
            draw.rectangle((x0, y, x0 + 5, y + 12), fill=post)
            y += 16
        draw.rectangle((x0 + 1, y0 + 3, x0 + 4, y1), fill=rail)
    else:
        x = x0
        while x < x1:
            draw.rectangle((x, y0, x + 5, y0 + 14), fill=post)
            x += 16
        draw.rectangle((x0, y0 + 4, x1, y0 + 8), fill=rail)


def _draw_numbers(draw, stroke=False):
    font = _font(12, bold=True)
    for spot_id, (x, y, w, h, _rotate) in SPOT_STALLS.items():
        text = str(spot_id)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx = x + (w - tw) / 2
        ty = y + (h - th) / 2 - 1
        if stroke:
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                draw.text((tx + dx, ty + dy), text, font=font, fill=(24, 28, 32))
        draw.text((tx, ty), text, font=font, fill=NUMBER)


def draw_numbers_on_top(image):
    _draw_numbers(ImageDraw.Draw(image), stroke=True)
    return image


def render_backdrop(key):
    width, height = CANVAS_SIZE
    image = Image.new("RGBA", CANVAS_SIZE, (*_grass_color(key), 255))
    draw = ImageDraw.Draw(image)
    winter = key == "winter"

    for x0, y0, x1, y1 in ASPHALT_RECTS:
        _rounded(draw, (x0 - 4, y0 - 4, x1 + 4, y1 + 4), 6, CURB)
    for x0, y0, x1, y1 in ASPHALT_RECTS:
        draw.rectangle((x0, y0, x1, y1), fill=ASPHALT)

    _rounded(draw, RED_ROOF, 6, (214, 232, 236) if winter else (196, 62, 54))
    _rounded(draw, WHITE_ROOF, 6, (236, 240, 242) if winter else (232, 234, 236))
    if winter:
        for box in (RED_ROOF, WHITE_ROOF):
            x0, y0, x1, y1 = box
            cap = image.crop(box)
            snow = Image.new("RGBA", cap.size, (244, 247, 250, 0))
            snow.putalpha(Image.new("L", cap.size, 170))
            image.alpha_composite(snow, (x0, y0))

    draw = ImageDraw.Draw(image)
    for x, y, w, h, _rotate in SPOT_STALLS.values():
        draw.rectangle((x, y, x + w - 1, y + h - 1), outline=LINE, width=1)
    for x, y, w, h, _rotate in QUEUE_SLOTS:
        draw.rectangle((x + 2, y + 2, x + w - 3, y + h - 3), outline=QUEUE_LINE, width=2)
    _draw_numbers(draw, stroke=False)

    _draw_fence(draw, 16, height - 22, width - 16, height - 6)
    _draw_fence(draw, width - 18, 8, width - 8, height - 16, vertical=True)

    assets = _load_assets()
    bush = assets.get("bush")
    tree = assets.get("tree")
    bare = assets.get("bare") or tree
    flowers = assets.get("flowers")
    if key.startswith("autumn") and bush is not None:
        bush = _tint(bush, (210, 120, 40), 0.55)
        tree = bare
    elif winter:
        bush = _tint(bush, (236, 240, 244), 0.45) if bush is not None else None
        tree = bare
    elif key.endswith("-rain") and bush is not None:
        bush = ImageEnhance.Brightness(bush).enhance(0.82)
        if tree is not None:
            tree = ImageEnhance.Brightness(tree).enhance(0.82)

    for cx, bottom in DECOR["bush"]:
        _paste_bottom(image, bush, cx, bottom, 42)
    for cx, bottom in DECOR["tree"]:
        _paste_bottom(image, tree, cx, bottom, 64)
    if flowers is not None and key in ("summer", "spring"):
        for cx, bottom in DECOR["flowers"]:
            _paste_bottom(image, flowers, cx, bottom, 28)
    _paste_bottom(image, assets.get("dumpster"), *DECOR["dumpster"], 40)
    barrier = assets.get("barrier")
    for cx, bottom in DECOR["barriers"]:
        _paste_bottom(image, barrier, cx, bottom, width=120)

    draw = ImageDraw.Draw(image)
    label = _font(11, bold=True)
    draw.text(DUMPSTER_LABEL, "Мусорный\nконтейнер", font=label, fill=(40, 48, 40))
    title = _font(28, bold=True)
    origin = (14, 6)
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        draw.text((origin[0] + dx, origin[1] + dy), "Схема парковки", font=title, fill=(255, 255, 255))
    draw.text(origin, "Схема парковки", font=title, fill=(48, 86, 52))
    return image


def ensure_parking_backdrop(day=None, temp=None, weather=None):
    key = backdrop_key(day, temp, weather)
    if os.path.exists(BACKDROP_PATH) and os.path.exists(KEY_PATH):
        with open(KEY_PATH, encoding="utf-8") as handle:
            if handle.read().strip() == key:
                return Image.open(BACKDROP_PATH).convert("RGBA")
    image = render_backdrop(key)
    os.makedirs(os.path.dirname(BACKDROP_PATH), exist_ok=True)
    image.save(BACKDROP_PATH)
    with open(KEY_PATH, "w", encoding="utf-8") as handle:
        handle.write(key)
    return image
