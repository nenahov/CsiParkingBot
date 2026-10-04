"""Координаты схемы: клетки мест, очередь 4×4, проезды и декор.

Кадр меньше 1280 по длинной стороне. Нос машины: 0 вверх, 180 вниз, -90 вправо.
Очередь заполняется снизу вверх, в ряду слева направо, все носом вниз.
"""

CANVAS_SIZE = (1080, 480)

CELL_W = 30
CELL_H = 48
CAR_SCALE = 0.46

ROW_X = 196
ROW_RIGHT = ROW_X + 17 * CELL_W  # 706

Y66 = 16
Y65 = 66
Y52 = 116
Y35 = 182
Y18 = 230
Y1 = 296
BOTTOM_ROAD_Y = 348

COL_X = 124
COL_W = 60
COL_H = 30
Y74 = 186

QUEUE_LIMIT = 16
QUEUE_COLS = 4
QUEUE_CELL_W = 46
QUEUE_CELL_H = 52
QUEUE_X = 868
QUEUE_PITCH_Y = 56
QUEUE_BOTTOM_Y = 248

RED_ROOF = (8, 150, 108, 400)
WHITE_ROOF = (718, 16, 792, 300)

# Прямоугольники асфальта (x0, y0, x1, y1). Яркость заливки держится ниже 90.
ASPHALT_RECTS = [
    (COL_X, Y35, ROW_RIGHT, 400),  # ряды 35–1, левый столбец и нижний проезд
    (ROW_X + 4 * CELL_W, Y52, ROW_RIGHT, Y35),  # ряд 52–64
    (ROW_X + 4 * CELL_W, Y65, ROW_X + 4 * CELL_W + 96, Y52),  # место 65
    (ROW_RIGHT - 3 * CELL_W, Y66, ROW_RIGHT, Y52),  # 66–68 и спуск к ряду 52
    (792, 8, 1064, 408),  # правый проезд
    (ROW_RIGHT, BOTTOM_ROAD_Y, 792, 400),  # поворот снизу на парковку
]

# Колеи: не заходят на клетки очереди (они правее x=868).
PARKING_LANES = [
    (ROW_X + 4 * CELL_W, Y52 + CELL_H, ROW_RIGHT, Y35),
    (ROW_X, Y18 + CELL_H, ROW_RIGHT, Y1),
    (ROW_X, BOTTOM_ROAD_Y, 840, 396),
    (804, 16, 856, 400),
]

# (x, y) — нижний центр спрайта.
DECOR = {
    "bush": [(70, 446), (360, 458), (700, 458), (1040, 448), (48, 128)],
    "tree": [(40, 142), (760, 462)],
    "flowers": [(210, 456), (560, 458), (900, 450)],
    "dumpster": (156, 158),
    "barriers": [(860, 30), (1000, 30)],
}

SNOWMAN_CENTER = (480, 468)
DUMPSTER_LABEL = (118, 128)

# Заезд сверху, по левой полосе правого проезда, снизу на парковку, к контейнеру.
GARBAGE_TRUCK_APPROACH = [
    (820, -40, 180), (820, 180, 180), (820, 360, 180),
    (620, 368, 90), (280, 368, 90), (148, 200, 0), (148, 112, 0),
]
GARBAGE_TRUCK_PAUSE = [(154, 108, 0), (144, 114, 8), (156, 106, -8), (148, 112, 0)]
GARBAGE_TRUCK_DEPARTURE = [
    (148, 200, 180), (280, 368, 270), (620, 368, 270),
    (820, 360, 0), (820, -40, 0),
]


def _build_stalls():
    stalls = {}

    def add_row(start, end, x0, y, cell_w, cell_h, rotate):
        for index, spot_id in enumerate(range(start, end + 1)):
            stalls[spot_id] = (x0 + index * cell_w, y, cell_w, cell_h, rotate)

    add_row(1, 17, ROW_X, Y1, CELL_W, CELL_H, 0)
    add_row(18, 34, ROW_X, Y18, CELL_W, CELL_H, 180)
    add_row(35, 51, ROW_X, Y35, CELL_W, CELL_H, 0)
    add_row(52, 64, ROW_X + 4 * CELL_W, Y52, CELL_W, CELL_H, 180)
    stalls[65] = (ROW_X + 4 * CELL_W, Y65, 96, CELL_H, 180)
    add_row(66, 68, ROW_RIGHT - 3 * CELL_W, Y66, CELL_W, CELL_H, 180)
    for index, spot_id in enumerate(range(74, 68, -1)):
        stalls[spot_id] = (COL_X, Y74 + index * COL_H, COL_W, COL_H, -90)
    return stalls


SPOT_STALLS = _build_stalls()


def _build_queue_slots():
    slots = []
    for index in range(QUEUE_LIMIT):
        col = index % QUEUE_COLS
        row_from_bottom = index // QUEUE_COLS
        x = QUEUE_X + col * QUEUE_CELL_W
        y = QUEUE_BOTTOM_Y - row_from_bottom * QUEUE_PITCH_Y
        slots.append((x, y, QUEUE_CELL_W, QUEUE_CELL_H, 180))
    return slots


QUEUE_SLOTS = _build_queue_slots()

PARKING_SPOT_AREAS = [
    (x, y, x + w, y + h) for x, y, w, h, _rotate in SPOT_STALLS.values()
]
PARKING_SPOT_AREAS.extend(
    (x, y, x + w, y + h) for x, y, w, h, _rotate in QUEUE_SLOTS
)
