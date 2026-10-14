import random
from datetime import datetime, timedelta

from models.driver import Driver
from utils.race_simulation import (
    BOOST_BONUS, HINDER_PENALTY, HINDER_TARGETS, RaceAction,
    action_from_dict, action_to_dict,
)

SELECTION_WINDOW = timedelta(minutes=10)


class GameState:
    __slots__ = (
        "player_ids", "wheels", "weather", "phase", "selection_deadline",
        "public_message_id", "actions", "race_seed", "confirmed",
    )

    def __init__(self, weather_forecast: dict, *, phase: str = "lobby"):
        self.player_ids = list()
        self.wheels = dict()
        self.weather = weather_forecast
        self.phase = phase
        self.selection_deadline = None
        self.public_message_id = None
        self.actions: dict[int, RaceAction] = {}
        self.race_seed = None
        self.confirmed: set[int] = set()

    def to_dict(self) -> dict:
        """Конвертация в «чистый» словарь для JSON."""
        return {
            "player_ids": self.player_ids,
            "wheels": self.wheels,
            "weather": self.weather,
            "phase": self.phase,
            "selection_deadline": self.selection_deadline,
            "public_message_id": self.public_message_id,
            "actions": {
                str(player_id): action_to_dict(action)
                for player_id, action in self.actions.items()
            },
            "race_seed": self.race_seed,
            "confirmed": sorted(self.confirmed),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GameState":
        """Восстановление из словаря."""
        # Здесь можно добавить валидацию наличия ключей
        obj = cls(weather_forecast=data["weather"], phase=data["phase"])
        obj.player_ids = data.get("player_ids", [])
        obj.wheels = data.get("wheels", {})
        obj.selection_deadline = data.get("selection_deadline")
        obj.public_message_id = data.get("public_message_id")
        obj.actions = {
            int(player_id): action_from_dict(action)
            for player_id, action in data.get("actions", {}).items()
        }
        obj.race_seed = data.get("race_seed")
        obj.confirmed = set(data["confirmed"])
        return obj

    def __repr__(self):
        return (f"{self.__class__.__name__}("
                f"player_ids={self.player_ids}, "
                f"wheels={self.wheels}, "
                f"weather={self.weather})")

    def is_in_game(self, player: Driver) -> bool:
        return player.id in self.player_ids

    def add_player(self, player: Driver):
        if self.phase != "lobby":
            raise ValueError("Registration is closed")
        if self.is_in_game(player):
            return
        self.player_ids.append(player.id)

    def set_wheels(self, player: Driver, wheels: int):
        self._require_selection(player.id)
        if wheels not in (0, 1, 2):
            raise ValueError("Invalid tire")
        self.wheels[str(player.id)] = wheels
        self.confirmed.discard(player.id)

    def _require_selection(self, player_id: int):
        if self.phase != "selection" or player_id not in self.player_ids:
            raise ValueError("Selection is closed or player is not registered")

    def begin_selection(self, now: datetime, seed: int):
        if self.phase != "lobby" or len(self.player_ids) < 7:
            raise ValueError("Not enough players or registration already closed")
        self.phase = "selection"
        self.selection_deadline = (now + SELECTION_WINDOW).isoformat()
        self.race_seed = seed

    def deadline_reached(self, now: datetime) -> bool:
        return (self.phase == "selection" and self.selection_deadline is not None
                and now >= datetime.fromisoformat(self.selection_deadline))

    def target_count(self) -> int:
        return min(HINDER_TARGETS, max(3, (len(self.player_ids) - 1) // 2))

    def choose_action(self, player_id: int, kind: str):
        self._require_selection(player_id)
        if kind == "boost":
            action = RaceAction(kind="boost", bonus=BOOST_BONUS)
        elif kind == "guard":
            action = RaceAction(kind="guard")
        elif kind == "neutral":
            action = RaceAction()
        elif kind == "hinder":
            action = RaceAction(kind="hinder", penalty=HINDER_PENALTY)
        else:
            raise ValueError("Invalid action")
        self.actions[player_id] = action
        self.confirmed.discard(player_id)

    def toggle_target(self, player_id: int, target_id: int):
        self._require_selection(player_id)
        action = self.actions.get(player_id)
        if action is None or action.kind != "hinder":
            raise ValueError("Select hinder first")
        if target_id == player_id or target_id not in self.player_ids:
            raise ValueError("Invalid target")
        selected = list(action.targets)
        if target_id in selected:
            selected.remove(target_id)
        elif len(selected) < self.target_count():
            selected.append(target_id)
        else:
            raise ValueError("All targets selected")
        self.actions[player_id] = RaceAction(
            kind="hinder", targets=tuple(selected), penalty=action.penalty,
        )
        self.confirmed.discard(player_id)

    def ready(self, player_id: int) -> bool:
        if str(player_id) not in self.wheels or player_id not in self.actions:
            return False
        action = self.actions[player_id]
        return action.kind != "hinder" or len(action.targets) == self.target_count()

    def all_ready(self) -> bool:
        return (self.phase == "selection" and bool(self.player_ids)
                and all(
                    player_id in self.confirmed and self.ready(player_id)
                    for player_id in self.player_ids
                ))

    def confirm(self, player_id: int):
        self._require_selection(player_id)
        if not self.ready(player_id):
            raise ValueError("Choose tires and a complete action first")
        self.confirmed.add(player_id)

    def resolve_actions(self) -> dict[int, RaceAction]:
        lane = {player_id: index for index, player_id in enumerate(self.player_ids)}
        return {
            lane[player_id]: RaceAction(
                kind=action.kind,
                targets=tuple(lane[target] for target in action.targets),
                bonus=action.bonus, penalty=action.penalty,
            )
            for player_id, action in self.actions.items()
        }

    def fill_missing_choices(self):
        if self.phase != "selection":
            raise ValueError("Selection is closed")
        for player_id in self.player_ids:
            self.wheels.setdefault(str(player_id), 0)
            if not self.ready(player_id):
                self.actions[player_id] = RaceAction()


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
