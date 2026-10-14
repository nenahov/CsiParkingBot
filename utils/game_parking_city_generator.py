"""Городская альтернатива случайной карте игры «Доберись до парковки»."""

import random

from utils.game_parking_utils import (
    CAR,
    EMPTY,
    FINISH,
    FUEL,
    INITIAL_FUEL,
    STONE,
    TREASURE,
    W_HEIGHT,
    W_WIDTH,
    GameState,
    can_reach_finish_with_fuel,
    is_path_exists,
    manhattan_distance,
)

ROADBLOCKS = ('🚧', '🏗')
CITY_BUILDINGS = ('🏡', '🏢', '🏣', '🏤', '🏥', '🏦', '🏨', '🏪', '🏬', '🏭', '🌳')
CITY_BUILDING_WEIGHTS = (6, 2, 1, 1, 1, 1, 1, 1, 1, 1, 2)


def generate_city_map_with_constraints(
        n, m, street_step=3, street_width=1, blocked_ratio=0.12,
        fuel_ratio=0.01, stone_ratio=0.03, min_distance=15,
        max_attempts=1000):
    """Сгенерировать карту с кварталами и перекрытыми участками улиц.

    Улицы образуют регулярную сетку. Вне улиц находятся здания; перекрёстки
    остаются открытыми для объезда. Результат проходит проверки бонуса и
    возможности доехать до парковки с учётом топлива.
    """
    if not isinstance(n, int) or not isinstance(m, int) or n <= 0 or m <= 0 or n * m < 3:
        raise ValueError("Размер карты должен содержать хотя бы три клетки.")
    if not isinstance(street_step, int) or street_step <= 0:
        raise ValueError("street_step должен быть положительным целым числом.")
    if not isinstance(street_width, int) or not 1 <= street_width <= street_step:
        raise ValueError("street_width должен быть от 1 до street_step.")
    if not isinstance(min_distance, int) or min_distance < 0:
        raise ValueError("min_distance должен быть неотрицательным целым числом.")
    if not isinstance(max_attempts, int) or max_attempts <= 0:
        raise ValueError("max_attempts должен быть положительным целым числом.")
    if any(not 0 <= ratio <= 1 for ratio in (blocked_ratio, fuel_ratio, stone_ratio)):
        raise ValueError("Доли перекрытий, заправок и препятствий должны быть от 0 до 1.")

    roads = [
        (x, y) for x in range(n) for y in range(m)
        if x % street_step < street_width or y % street_step < street_width
    ]
    road_set = set(roads)
    segments = {
        (x, y) for x, y in roads
        if (x % street_step < street_width) != (y % street_step < street_width)
    }
    num_blocked = int(blocked_ratio * len(roads))
    num_fuels = int(fuel_ratio * n * m)
    num_stones = int(stone_ratio * n * m)
    if len(roads) < 3 + num_blocked + num_fuels + num_stones:
        raise ValueError("Для городской карты не хватает клеток улиц.")
    if num_blocked > len(segments):
        raise ValueError("Для заданного числа перекрытий не хватает участков улиц.")

    for _ in range(max_attempts):
        map_matrix = [
            [
                EMPTY if (x, y) in road_set else
                random.choices(CITY_BUILDINGS, weights=CITY_BUILDING_WEIGHTS, k=1)[0]
                for y in range(m)
            ]
            for x in range(n)
        ]
        available_roads = roads.copy()
        random.shuffle(available_roads)

        start = available_roads.pop()
        possible_finishes = [
            coord for coord in available_roads
            if manhattan_distance(start, coord) >= min_distance
        ]
        if not possible_finishes:
            continue
        finish = random.choice(possible_finishes)
        available_roads.remove(finish)
        possible_treasures = [
            coord for coord in available_roads
            if manhattan_distance(start, coord) >= min_distance
        ]
        treasure = random.choice(possible_treasures or available_roads)
        available_roads.remove(treasure)

        map_matrix[start[0]][start[1]] = CAR
        map_matrix[finish[0]][finish[1]] = FINISH
        map_matrix[treasure[0]][treasure[1]] = TREASURE

        # Закрываем только сегменты улиц, оставляя перекрёстки для объезда.
        street_segments = [coord for coord in available_roads if coord in segments]
        if len(street_segments) < num_blocked:
            continue
        for x, y in random.sample(street_segments, num_blocked):
            available_roads.remove((x, y))
            map_matrix[x][y] = random.choice(ROADBLOCKS)
        for _ in range(num_fuels):
            x, y = available_roads.pop()
            map_matrix[x][y] = FUEL
        for _ in range(num_stones):
            x, y = available_roads.pop()
            map_matrix[x][y] = STONE

        if (is_path_exists(map_matrix, TREASURE, forbidden=(FINISH,))
                and can_reach_finish_with_fuel(map_matrix)):
            window_x = min(n - W_WIDTH + 1, max(-1, start[0] - ((W_WIDTH - 1) // 2)))
            window_y = min(m - W_HEIGHT + 1, max(-1, start[1] - ((W_HEIGHT - 1) // 2)))
            return GameState(start[0], start[1], INITIAL_FUEL, window_x, window_y, map_matrix)

    raise ValueError("Не удалось сгенерировать городскую карту с заданными ограничениями.")


# Пример использования
if __name__ == "__main__":
    n, m = 17, 13
    # game_state = generate_map_with_constraints(n, m, wall_ratio=0.4)
    game_state = generate_city_map_with_constraints(17, 13)
    print(game_state.get_map())
    print(game_state.x, game_state.y)
    print(game_state.wx, game_state.wy)
    print(game_state.get_map_section())
