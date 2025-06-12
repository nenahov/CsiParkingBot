import random

from models.driver import Driver


class GameState:
    __slots__ = ("player_ids", "wheels", "weather")  # экономит память и запрещает новые атрибуты

    def __init__(self, weather_forecast: dict):
        self.player_ids = list()
        self.wheels = dict()
        self.weather = weather_forecast

    def to_dict(self) -> dict:
        """Конвертация в «чистый» словарь для JSON."""
        return {
            "player_ids": self.player_ids,
            "wheels": self.wheels,
            "weather": self.weather
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GameState":
        """Восстановление из словаря."""
        # Здесь можно добавить валидацию наличия ключей
        obj = cls(weather_forecast=data.get("weather", {}))
        obj.player_ids = data.get("player_ids", [])
        obj.wheels = data.get("wheels", {})
        return obj

    def __repr__(self):
        return (f"{self.__class__.__name__}("
                f"player_ids={self.player_ids}, "
                f"wheels={self.wheels}, "
                f"weather={self.weather})")

    def is_in_game(self, player: Driver) -> bool:
        return player.id in self.player_ids

    def add_player(self, player: Driver):
        if self.is_in_game(player):
            return
        self.player_ids.append(player.id)

    def set_wheels(self, player: Driver, wheels: int):
        self.wheels[player.id] = wheels


def generate_game_with_weather_forecast():
    """
    Для двух сегментов генерируем случайный прогноз погоды и создаем новое состояние игры "Гонки"
    :return: состояние игры
    """
    weather_forecast = dict()

    # Генерируем случайный прогноз погоды
    weather_forecast['1'] = random_triplet_sum_10()
    weather_forecast['2'] = random_triplet_sum_10()

    return GameState(weather_forecast)


def random_triplet_sum_10():
    # Первое число от 0 до 10
    a = random.randint(0, 10)
    # Второе число от 0 до (10 - a)
    b = random.randint(0, 10 - a)
    # Третье число — остаток, чтобы сумма была 10
    c = 10 - a - b
    return a, b, c


# Пример использования
if __name__ == "__main__":
    game_state = generate_game_with_weather_forecast()
    print(game_state)
