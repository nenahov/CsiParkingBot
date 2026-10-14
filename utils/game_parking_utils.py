import random
from collections import deque

# Константы символов
EMPTY = '◻️'
EMPTY2 = '◽️'
WALLS = ['🌲', '🏡', '🌳', '🌲', '🛸', '🚧', '🏗', '🏛', '🏢', '🏣', '🏤', '🏥', '🏦', '🏨', '🏩', '🏪', '🏬', '🏭', '💒']
WALL_WEIGHTS = [0, 800, 50, 50, 1, 20, 20, 10, 10, 10, 10, 10, 10, 10, 10, 20, 10, 10, 10]
FINISH = '🅿️'
TREASURE = '🫶'
CAR = '🚘'
FUEL = '⛽️'
STONE = '🚓'

W_WIDTH = 7
W_HEIGHT = 7
INITIAL_FUEL = 50
MAX_FUEL = 100
FUEL_PICKUP = 50
STONE_PENALTY = 10
DIRECTIONS = ((-1, 0), (1, 0), (0, -1), (0, 1))


class GameState:
    """Игровое состояние. map_matrix[x][y]: x — колонка, y — строка."""

    __slots__ = ("x", "y", "fuel", "map_matrix", "wx", "wy",
                 "car_on_parking")  # экономит память и запрещает новые атрибуты

    def __init__(self, x: int, y: int, fuel: int, wx: int, wy: int, map_matrix):
        self.x = x
        self.y = y
        self.fuel = fuel
        self.wx = wx
        self.wy = wy
        self.car_on_parking = False
        self.map_matrix = map_matrix

    def __repr__(self):
        return f"{self.__class__.__name__}(x={self.x}, y={self.y})"

    def is_wall(self, dx, dy) -> bool:
        if (dx, dy) not in DIRECTIONS:
            return True
        new_x = max(0, min(len(self.map_matrix) - 1, self.x + dx))
        new_y = max(0, min(len(self.map_matrix[0]) - 1, self.y + dy))
        if (new_x, new_y) == (self.x, self.y):
            return True
        return self.map_matrix[new_x][new_y] in WALLS

    def move(self, dx, dy):
        if self.is_end_game() or self.is_wall(dx, dy):
            return None
        new_x = max(0, min(len(self.map_matrix) - 1, self.x + dx))
        new_y = max(0, min(len(self.map_matrix[0]) - 1, self.y + dy))
        item = self.map_matrix[new_x][new_y]
        self.fuel = max(0, self.fuel - 1)
        self.apply(item)
        self.map_matrix[self.x][self.y] = EMPTY2
        self.map_matrix[new_x][new_y] = CAR
        self.x = new_x
        self.y = new_y
        return item

    def apply(self, item):
        if item == FUEL:
            self.fuel = min(MAX_FUEL, self.fuel + FUEL_PICKUP)
        elif item == STONE:
            self.fuel = max(0, self.fuel - STONE_PENALTY)
        elif item == FINISH:
            self.fuel = min(MAX_FUEL, self.fuel + 1)
            self.car_on_parking = True

    def get_map_section(self):
        n, m = len(self.map_matrix), len(self.map_matrix[0])
        # Подвинем окно вслед за машиной
        if self.x - 2 < self.wx:
            self.wx = max(-1, self.x - 2)
        if self.y - 2 < self.wy:
            self.wy = max(-1, self.y - 2)
        if self.x + 2 >= self.wx + W_WIDTH:
            self.wx = min(n - W_WIDTH + 1, self.x + 2 - W_WIDTH + 1)
        if self.y + 2 >= self.wy + W_HEIGHT:
            self.wy = min(m - W_HEIGHT + 1, self.y + 2 - W_HEIGHT + 1)

        result = ''
        for j in range(self.wy, self.wy + W_HEIGHT):
            for i in range(self.wx, self.wx + W_WIDTH):
                if 0 <= i < n and 0 <= j < m:
                    result += self.map_matrix[i][j]
                else:
                    result += WALLS[0]  # За пределами — символ стены
            result += '\n'
        return result

    def get_map(self):
        n, m = len(self.map_matrix), len(self.map_matrix[0])

        result = ''
        for j in range(-1, m + 1):
            for i in range(-1, n + 1):
                if 0 <= i < n and 0 <= j < m:
                    result += self.map_matrix[i][j]
                else:
                    result += WALLS[0]  # За пределами — символ стены
            result += '\n'
        return result

    def is_end_game(self):
        return self.car_on_parking or self.fuel <= 0

    def is_win(self):
        return self.car_on_parking


def manhattan_distance(p1, p2):
    return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])


def generate_map_with_constraints(n, m, wall_ratio=0.3, fuel_ratio=0.01, stone_ratio=0.03, min_distance=15,
                                  max_attempts=1000):
    if not isinstance(n, int) or not isinstance(m, int) or n <= 0 or m <= 0 or n * m < 3:
        raise ValueError("Размер карты должен содержать хотя бы три клетки.")
    if not isinstance(min_distance, int) or min_distance < 0:
        raise ValueError("min_distance должен быть неотрицательным целым числом.")
    if not isinstance(max_attempts, int) or max_attempts <= 0:
        raise ValueError("max_attempts должен быть положительным целым числом.")
    if any(not 0 <= ratio <= 1 for ratio in (wall_ratio, fuel_ratio, stone_ratio)):
        raise ValueError("Доли стен, заправок и препятствий должны быть от 0 до 1.")
    num_walls = int(wall_ratio * n * m)
    num_fuels = int(fuel_ratio * n * m)
    num_stones = int(stone_ratio * n * m)
    if num_walls + num_fuels + num_stones > n * m - 3:
        raise ValueError("Для всех объектов не хватает свободных клеток.")

    for _ in range(max_attempts):
        map_matrix = [[EMPTY for _ in range(m)] for _ in range(n)]
        all_coords = [(i, j) for i in range(n) for j in range(m)]
        random.shuffle(all_coords)

        start = all_coords.pop()
        possible_finishes = [coord for coord in all_coords if manhattan_distance(start, coord) >= min_distance]
        if not possible_finishes:
            continue

        finish = random.choice(possible_finishes)
        all_coords.remove(finish)
        possible_finishes.remove(finish)

        # Бонус по возможности тоже удалён от старта, но это не обязательное условие.
        treasure = random.choice(possible_finishes or all_coords)
        all_coords.remove(treasure)

        map_matrix[start[0]][start[1]] = CAR
        map_matrix[finish[0]][finish[1]] = FINISH
        map_matrix[treasure[0]][treasure[1]] = TREASURE

        for _ in range(num_walls):
            i, j = all_coords.pop()
            map_matrix[i][j] = random.choices(WALLS, weights=WALL_WEIGHTS, k=1)[0]

        for _ in range(num_fuels):
            i, j = all_coords.pop()
            map_matrix[i][j] = FUEL

        for _ in range(num_stones):
            i, j = all_coords.pop()
            map_matrix[i][j] = STONE

        # Бонус должен быть достижим до финиша: проезд через парковку
        # завершает игру и уже не позволяет забрать бонус.
        if (is_path_exists(map_matrix, TREASURE, forbidden=(FINISH,))
                and can_reach_finish_with_fuel(map_matrix)):
            return GameState(start[0], start[1], INITIAL_FUEL,
                             min(n - W_WIDTH + 1, max(-1, start[0] - ((W_WIDTH - 1) // 2))),
                             min(m - W_HEIGHT + 1, max(-1, start[1] - ((W_HEIGHT - 1) // 2))), map_matrix)

    raise ValueError("Не удалось сгенерировать карту с заданным расстоянием и проходимостью.")


def _find_symbol(map_matrix, symbol):
    return next(((x, y) for x, column in enumerate(map_matrix)
                 for y, item in enumerate(column) if item == symbol), None)


def _is_rectangular_map(map_matrix):
    return bool(map_matrix and map_matrix[0]) and all(
        len(column) == len(map_matrix[0]) for column in map_matrix
    )


def is_path_exists(map_matrix, target=FINISH, forbidden=()):
    if not _is_rectangular_map(map_matrix):
        return False
    n, m = len(map_matrix), len(map_matrix[0])
    start = _find_symbol(map_matrix, CAR)
    finish = _find_symbol(map_matrix, target)
    if start is None or finish is None:
        return False

    queue = deque([start])
    visited = {start}

    while queue:
        x, y = queue.popleft()
        if (x, y) == finish:
            return True
        for dx, dy in DIRECTIONS:
            nx, ny = x + dx, y + dy
            if (0 <= nx < n and 0 <= ny < m
                    and map_matrix[nx][ny] not in WALLS
                    and map_matrix[nx][ny] not in forbidden
                    and (nx, ny) not in visited):
                visited.add((nx, ny))
                queue.append((nx, ny))
    return False


def can_reach_finish_with_fuel(map_matrix):
    """Проверить возможность победы с однократным подбором каждой заправки."""
    if not _is_rectangular_map(map_matrix):
        return False
    start = _find_symbol(map_matrix, CAR)
    if start is None or _find_symbol(map_matrix, FINISH) is None:
        return False

    n, m = len(map_matrix), len(map_matrix[0])
    fuels = {(x, y): 1 << index for index, (x, y) in enumerate(
        (x, y) for x in range(n) for y in range(m) if map_matrix[x][y] == FUEL
    )}
    queue = deque([(start[0], start[1], INITIAL_FUEL, 0)])
    # При одинаковых координатах и подобранных заправках больший остаток
    # топлива всегда не хуже меньшего.
    best_fuel = {(start[0], start[1], 0): INITIAL_FUEL}
    while queue:
        x, y, fuel, collected = queue.popleft()
        if fuel < best_fuel[x, y, collected]:
            continue
        for dx, dy in DIRECTIONS:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < n and 0 <= ny < m):
                continue
            item = map_matrix[nx][ny]
            if item in WALLS:
                continue
            if item == FINISH:
                return True  # Финиш добавляет 1 после расхода на последний ход.
            next_fuel = fuel - 1
            next_collected = collected
            if item == STONE:
                next_fuel = max(0, next_fuel - STONE_PENALTY)
            elif item == FUEL:
                bit = fuels[nx, ny]
                if not collected & bit:
                    next_fuel = min(MAX_FUEL, next_fuel + FUEL_PICKUP)
                    next_collected |= bit
            if next_fuel <= 0:
                continue
            key = (nx, ny, next_collected)
            if next_fuel > best_fuel.get(key, -1):
                best_fuel[key] = next_fuel
                queue.append((nx, ny, next_fuel, next_collected))
    return False


# Пример использования
if __name__ == "__main__":
    n, m = 17, 13
    game_state = generate_map_with_constraints(n, m, wall_ratio=0.4)
    print(game_state.get_map())
    print(game_state.x, game_state.y)
    print(game_state.wx, game_state.wy)
    print(game_state.get_map_section())
