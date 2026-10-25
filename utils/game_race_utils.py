import random
from datetime import datetime, timedelta

from models.driver import Driver
from utils.race_simulation import (
    NITRO_RULES_VERSION, RaceAction,
    action_from_dict, action_to_dict,
)

SELECTION_WINDOW = timedelta(hours=1)


class GameState:
    """Состояние одной гонки: участники, тайные решения и срок выбора."""
    __slots__ = (
        "player_ids", "wheels", "weather", "phase", "selection_deadline",
        "public_message_id", "actions", "race_seed", "confirmed",
        "rules_version",
    )

    def __init__(self, weather_forecast: dict, *, phase: str = "lobby"):
        """Создать лобби с прогнозом погоды для будущего заезда."""
        self.player_ids = list()
        self.wheels = dict()
        self.weather = weather_forecast
        self.phase = phase
        self.selection_deadline = None
        self.public_message_id = None
        self.actions: dict[int, RaceAction] = {}
        self.race_seed = None
        self.confirmed: set[int] = set()
        self.rules_version = NITRO_RULES_VERSION

    def to_dict(self) -> dict:
        """Сохранить состояние в словарь, пригодный для JSON."""
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
            "rules_version": self.rules_version,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GameState":
        """Восстановить состояние, включая выборы и версию правил."""
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
        obj.rules_version = data.get("rules_version", "risk-intrigue-5")
        return obj

    def __repr__(self):
        """Показать краткое состояние для диагностики."""
        return (f"{self.__class__.__name__}("
                f"player_ids={self.player_ids}, "
                f"wheels={self.wheels}, "
                f"weather={self.weather})")

    def is_in_game(self, player: Driver) -> bool:
        """Проверить, зарегистрирован ли водитель в гонке."""
        return player.id in self.player_ids

    def add_player(self, player: Driver):
        """Добавить водителя, пока открыт набор участников."""
        if self.phase != "lobby":
            raise ValueError("Registration is closed")
        if self.is_in_game(player):
            return
        self.player_ids.append(player.id)

    def set_wheels(self, player: Driver, wheels: int):
        """Выбрать шины и снять прежнее подтверждение решения."""
        self._require_selection(player.id)
        if wheels not in (0, 1, 2):
            raise ValueError("Invalid tire")
        self.wheels[str(player.id)] = wheels
        self.confirmed.discard(player.id)

    def _require_selection(self, player_id: int):
        """Запретить изменение выбора вне открытого окна и посторонним."""
        if self.phase != "selection" or player_id not in self.player_ids:
            raise ValueError("Selection is closed or player is not registered")

    def begin_selection(self, now: datetime, seed: int):
        """Закрыть набор и открыть часовое окно тайных решений."""
        if self.phase != "lobby" or len(self.player_ids) < 7:
            raise ValueError("Not enough players or registration already closed")
        self.phase = "selection"
        self.selection_deadline = (now + SELECTION_WINDOW).isoformat()
        self.race_seed = seed
        self.rules_version = NITRO_RULES_VERSION

    def migrate_legacy_selection(self, now: datetime):
        """Сохранить состав и шины, сбросить старые карты и дать новый час."""
        if self.phase != "selection" or self.rules_version == NITRO_RULES_VERSION:
            return False
        self.actions.clear()
        self.confirmed.clear()
        self.selection_deadline = (now + SELECTION_WINDOW).isoformat()
        self.rules_version = NITRO_RULES_VERSION
        return True

    def deadline_reached(self, now: datetime) -> bool:
        """Проверить, закончился ли срок подтверждения решений."""
        return (self.phase == "selection" and self.selection_deadline is not None
                and now >= datetime.fromisoformat(self.selection_deadline))

    def target_count(self) -> int:
        """Вернуть число обязательных перевозок и предел защит: от 3 до 5."""
        return min(5, max(3, (len(self.player_ids) - 1) // 2))

    def _nitro_action(self, player_id: int) -> RaceAction:
        """Взять текущее решение или пустое решение по новым правилам."""
        return self.actions.get(player_id, RaceAction(kind="nitro"))

    def choose_plan(self, player_id: int, plan: str):
        """Задать время расхода нитро, сохранив перевозки и защиту."""
        self._require_selection(player_id)
        if plan not in ("early", "steady", "late"):
            raise ValueError("Invalid plan")
        action = self._nitro_action(player_id)
        self.actions[player_id] = RaceAction(
            kind="nitro", transfers=action.transfers,
            guards=action.guards, plan=plan,
        )
        self.confirmed.discard(player_id)

    def set_transfer(self, player_id: int, slot: int, role: str, target_id: int):
        """Указать источник или получателя в выбранной паре перевозки.

        Незаполненная сторона хранится как -1; такую пару нельзя подтвердить.
        Источники и получатели не должны повторяться в своих колонках.
        """
        self._require_selection(player_id)
        if target_id == player_id or target_id not in self.player_ids:
            raise ValueError("Invalid target")
        if not 0 <= slot < self.target_count() or role not in ("source", "recipient"):
            raise ValueError("Invalid transfer slot")
        action = self._nitro_action(player_id)
        # До подтверждения незаполненная сторона пары обозначается числом -1.
        selected = list(action.transfers)
        while len(selected) <= slot:
            selected.append((-1, -1))
        pair = list(selected[slot])
        pair[0 if role == "source" else 1] = target_id
        if pair[0] == pair[1]:
            raise ValueError("Source and recipient must differ")
        selected[slot] = tuple(pair)
        column = 0 if role == "source" else 1
        if len({pair[column] for pair in selected if pair[column] != -1}) != sum(
                pair[column] != -1 for pair in selected):
            raise ValueError("Choose distinct players in each column")
        self.actions[player_id] = RaceAction(
            kind="nitro", transfers=tuple(selected),
            guards=action.guards, plan=action.plan,
        )
        self.confirmed.discard(player_id)

    def toggle_guard(self, player_id: int, target_id: int):
        """Включить или снять защиту от действий конкретного соперника."""
        self._require_selection(player_id)
        if target_id == player_id or target_id not in self.player_ids:
            raise ValueError("Invalid guard")
        action = self._nitro_action(player_id)
        guards = list(action.guards)
        if target_id in guards:
            guards.remove(target_id)
        elif len(guards) < self.target_count():
            guards.append(target_id)
        else:
            raise ValueError("All guards selected")
        self.actions[player_id] = RaceAction(
            kind="nitro", transfers=action.transfers,
            guards=tuple(guards), plan=action.plan,
        )
        self.confirmed.discard(player_id)

    def ready(self, player_id: int) -> bool:
        """Проверить наличие шин и всех полностью заполненных перевозок."""
        if str(player_id) not in self.wheels or player_id not in self.actions:
            return False
        action = self.actions[player_id]
        return (action.kind == "nitro"
                and len(action.transfers) == self.target_count()
                and all(source != -1 and recipient != -1
                        for source, recipient in action.transfers))

    def all_ready(self) -> bool:
        """Проверить, подтвердили ли все водители полный выбор."""
        return (self.phase == "selection" and bool(self.player_ids)
                and all(
                    player_id in self.confirmed and self.ready(player_id)
                    for player_id in self.player_ids
                ))

    def confirm(self, player_id: int):
        """Подтвердить личное решение, если обязательные поля заполнены."""
        self._require_selection(player_id)
        if not self.ready(player_id):
            raise ValueError("Choose tires and a complete action first")
        self.confirmed.add(player_id)

    def resolve_actions(self) -> dict[int, RaceAction]:
        """Заменить идентификаторы водителей индексами полос для симуляции."""
        lane = {player_id: index for index, player_id in enumerate(self.player_ids)}
        return {
            lane[player_id]: RaceAction(
                kind=action.kind,
                transfers=tuple((lane[source], lane[recipient])
                                for source, recipient in action.transfers),
                guards=tuple(lane[target] for target in action.guards),
                plan=action.plan,
            )
            for player_id, action in self.actions.items()
        }

    def fill_missing_choices(self):
        """По тайм-ауту назначить шины по умолчанию и убрать неполные заявки."""
        if self.phase != "selection":
            raise ValueError("Selection is closed")
        for player_id in self.player_ids:
            self.wheels.setdefault(str(player_id), 0)
            if not self.ready(player_id):
                self.actions[player_id] = RaceAction(kind="nitro")


def generate_game_with_weather_forecast():
    """Создать лобби гонки со случайным прогнозом первых двух участков."""
    weather_forecast = dict()

    # Генерируем случайный прогноз погоды
    weather_forecast['1'] = random_triplet_sum_10()
    weather_forecast['2'] = random_triplet_sum_10()

    return GameState(weather_forecast)


def random_triplet_sum_10():
    """Получить три неотрицательных веса погоды с суммой десять."""
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
