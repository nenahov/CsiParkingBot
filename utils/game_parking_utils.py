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


class GameState:
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

    def __eq__(self, other):
        if not isinstance(other, GameState):
            return NotImplemented
        return (self.x, self.y) == (other.x, other.y)

    def is_wall(self, dx, dy) -> bool:
        new_x = max(0, min(len(self.map_matrix) - 1, self.x + dx))
        new_y = max(0, min(len(self.map_matrix[0]) - 1, self.y + dy))
        if (new_x, new_y) == (self.x, self.y):
            return True
        return self.map_matrix[new_x][new_y] in WALLS

    def move(self, dx, dy):
        new_x = max(0, min(len(self.map_matrix) - 1, self.x + dx))
        new_y = max(0, min(len(self.map_matrix[0]) - 1, self.y + dy))
        if (new_x, new_y) == (self.x, self.y):
            return None
        item = self.map_matrix[new_x][new_y]
        if not (item in WALLS):
            self.fuel = max(0, self.fuel - 1)
            self.apply(item)
            self.map_matrix[self.x][self.y] = EMPTY2
            self.map_matrix[new_x][new_y] = CAR
            self.x = new_x
            self.y = new_y
            return item
        return None

    def apply(self, item):
        if item == FUEL:
            self.fuel = min(100, self.fuel + 50)
        elif item == STONE:
            self.fuel = max(0, self.fuel - 10)
        elif item == FINISH:
            self.fuel = min(100, self.fuel + 1)
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

        treasure = random.choice(possible_finishes)
        all_coords.remove(treasure)

        map_matrix[start[0]][start[1]] = CAR
        map_matrix[finish[0]][finish[1]] = FINISH
        map_matrix[treasure[0]][treasure[1]] = TREASURE

        num_walls = int(wall_ratio * n * m)
        for _ in range(num_walls):
            if not all_coords: break
            i, j = all_coords.pop()
            map_matrix[i][j] = random.choices(WALLS, weights=WALL_WEIGHTS, k=1)[0]

        num_fuels = int(fuel_ratio * n * m)
        for _ in range(num_fuels):
            if not all_coords: break
            i, j = all_coords.pop()
            if map_matrix[i][j] == EMPTY:
                map_matrix[i][j] = FUEL

        num_stones = int(stone_ratio * n * m)
        for _ in range(num_stones):
            if not all_coords: break
            i, j = all_coords.pop()
            if map_matrix[i][j] == EMPTY:
                map_matrix[i][j] = STONE

        if is_path_exists(map_matrix):
            return GameState(start[0], start[1], 50, min(n - W_WIDTH + 1, max(-1, start[0] - ((W_WIDTH - 1) // 2))),
                             min(m - W_HEIGHT + 1, max(-1, start[1] - ((W_HEIGHT - 1) // 2))), map_matrix)

    raise ValueError("Не удалось сгенерировать карту с заданным расстоянием и проходимостью.")


def is_path_exists(map_matrix):
    n, m = len(map_matrix), len(map_matrix[0])
    start = None
    finish = None
    for i in range(n):
        for j in range(m):
            if map_matrix[i][j] == CAR:
                start = (i, j)
            if map_matrix[i][j] == FINISH:
                finish = (i, j)

    directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    queue = deque([start])
    visited = {start}

    while queue:
        x, y = queue.popleft()
        if (x, y) == finish:
            return True
        for dx, dy in directions:
            nx, ny = x + dx, y + dy
            if 0 <= nx < n and 0 <= ny < m and map_matrix[nx][ny] not in WALLS and (nx, ny) not in visited:
                visited.add((nx, ny))
                queue.append((nx, ny))
    return False


# Пример использования
if __name__ == "__main__":
    n, m = 20, 30
    game_state = generate_map_with_constraints(n, m, wall_ratio=0.4)
    print(game_state.get_map())
    print(game_state.x, game_state.y)
    print(game_state.wx, game_state.wy)
    print(game_state.get_map_section())
