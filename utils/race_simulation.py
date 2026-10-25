"""Расчёт гонки без зависимостей от Telegram, базы данных и отрисовки.

Новые правила сначала распределяют нитро, затем рассчитывают движение.
Старые правила оставлены для сравнения в историческом симуляторе баланса.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Mapping, Sequence

RACE_ENTRY_FEE = 50
RACE_RULES_VERSION = "risk-intrigue-5"
NITRO_RULES_VERSION = "nitro-transfer-1"
NITRO_PULSE_FRAMES = 5
NITRO_SPEED_BONUS = .55
# Сцепление меняет силу рывка: прогноз помогает выбрать момент расхода.
NITRO_WEATHER_MULTIPLIERS = (1.0, .65, 1.30)  # cloud, rain, sun
BOOST_BONUS = 0.05
HINDER_TARGETS = 5
HINDER_PENALTY = 0.10
GUARD_ABSORPTION = 0.5
PLACE_WEIGHTS = (35, 25, 17, 12, 8)
SEGMENTS = 3
MIN_SPEED_FACTOR = 0.01  # В старых правилах даже массовая атака не останавливает машину.
# Старые диапазоны: сначала погода (облака, дождь, солнце), затем тип шин.
SPEED_RANGES = (
    ((.15, .40), (.00, .10), (.05, .20)),
    ((.05, .20), (.40, .80), (.00, .05)),
    ((.05, .20), (.00, .05), (.30, .70)),
)


@dataclass(frozen=True)
class RaceAction:
    """Тайное решение водителя: перевозки, защита и план расхода нитро.

    Поля targets/bonus/penalty нужны только исторической версии гонки.
    Индексы игроков в симуляции начинаются с нуля.
    """
    kind: str = "neutral"
    targets: tuple[int, ...] = ()
    bonus: float = BOOST_BONUS
    penalty: float = HINDER_PENALTY
    transfers: tuple[tuple[int, int], ...] = ()
    guards: tuple[int, ...] = ()
    plan: str = "steady"


def action_to_dict(action: RaceAction) -> dict:
    """Преобразовать решение в словарь для сохранения состояния гонки."""
    return {
        "kind": action.kind,
        "targets": list(action.targets),
        "bonus": action.bonus,
        "penalty": action.penalty,
        "transfers": [list(pair) for pair in action.transfers],
        "guards": list(action.guards),
        "plan": action.plan,
    }


def action_from_dict(data: dict) -> RaceAction:
    """Восстановить решение из JSON-совместимого словаря."""
    return RaceAction(
        kind=data.get("kind", "neutral"),
        targets=tuple(int(target) for target in data.get("targets", ())),
        bonus=float(data.get("bonus", BOOST_BONUS)),
        penalty=float(data.get("penalty", HINDER_PENALTY)),
        transfers=tuple((int(source), int(target))
                        for source, target in data.get("transfers", ())),
        guards=tuple(int(target) for target in data.get("guards", ())),
        plan=data.get("plan", "steady"),
    )


@dataclass(frozen=True)
class SpeedSpan:
    """Участок движения с постоянной скоростью от указанного кадра."""
    frame: int
    position: float
    speed: float


@dataclass
class RaceSimulationResult:
    """Итоги заезда и данные для покадровой отрисовки того же результата."""
    winners: list[int]
    weather_segments: list[int]
    spans: list[list[SpeedSpan]]
    events: list[dict]
    prizes: dict[int, int]
    finish_frames: list[int | None]
    forecast: dict[str, list[int]]
    wheels: list[int]
    seed: int
    frame_count: int
    nitro: list[int] | None = None
    nitro_pulses: list[tuple[int, ...]] | None = None

    def position_at(self, racer: int, frame: int) -> float:
        """Вернуть пройденное расстояние гонщика к указанному кадру."""
        spans = self.spans[racer]
        # Перебор смен скорости дешевле хранения позиции каждого кадра.
        span = spans[0]
        for candidate in spans[1:]:
            if candidate.frame > frame:
                break
            span = candidate
        return span.position + (frame - span.frame) * span.speed


def allocate_prizes(players_count: int, fee: int = RACE_ENTRY_FEE) -> dict[int, int]:
    """Распределить весь фонд взносов по местам, начиная с первого."""
    if players_count < 2 or fee < 0:
        raise ValueError("Race needs at least two players and a nonnegative fee")
    pool = players_count * fee
    last_prize = min(fee, pool)
    remaining = pool - last_prize
    weights = PLACE_WEIGHTS[: min(5, players_count - 1)]
    total_weight = sum(weights)
    quotients = [remaining * weight / total_weight for weight in weights]
    amounts = [math.floor(value) for value in quotients]
    remainders = sorted(
        range(len(weights)), key=lambda index: (quotients[index] - amounts[index], -index),
        reverse=True,
    )
    for index in remainders[: remaining - sum(amounts)]:
        amounts[index] += 1
    return {**{place: prize for place, prize in enumerate(amounts, 1)},
            players_count: last_prize}


def _forecast(rng: random.Random) -> dict[str, list[int]]:
    """Сгенерировать вероятности трёх типов погоды для двух участков."""
    result = {}
    for number in (1, 2):
        cloud = rng.randint(0, 10)
        rain = rng.randint(0, 10 - cloud)
        result[str(number)] = [cloud, rain, 10 - cloud - rain]
    return result


def generate_forecast(seed: int) -> dict[str, list[int]]:
    """Получить воспроизводимый прогноз по зерну случайности гонки."""
    return _forecast(random.Random(seed ^ 0x71A5EED))


def _weather(
        rng: random.Random, wheels: Sequence[int], forecast: Mapping[str, Sequence[int]]
) -> list[int]:
    """Определить общую погоду участков с учётом прогноза и выбранных шин."""
    result = [rng.choices((0, 1, 2), weights=forecast[str(i)], k=1)[0]
              for i in (1, 2)]
    counts = [wheels.count(tire) for tire in range(3)]
    least = min(counts)
    # Учитываем даже невыбранные типы шин: их количество равно нулю.
    result.append(rng.choice([tire for tire, count in enumerate(counts) if count == least]))
    return result


def _resolve_actions(
        rng: random.Random, count: int, actions: Mapping[int, RaceAction],
        *, guard_absorption: float, hinder_segment_mode: str,
) -> tuple[list[list[float]], list[dict]]:
    """Рассчитать форсаж, помехи и защиту для старых правил гонки."""
    modifiers = [[0.0] * SEGMENTS for _ in range(count)]
    events: list[dict] = []
    for actor in sorted(actions):
        if not 0 <= actor < count:
            raise ValueError(f"Invalid actor {actor}")
        action = actions[actor]
        if action.kind not in ("neutral", "boost", "hinder", "guard"):
            raise ValueError(f"Invalid action {action.kind}")
        if action.kind == "boost":
            segment = rng.randrange(SEGMENTS)
            modifiers[actor][segment] += action.bonus
            events.append({"kind": "boost", "actor": actor, "target": actor,
                           "segment": segment, "status": "success"})
        elif action.kind == "hinder":
            if len(action.targets) != len(set(action.targets)):
                raise ValueError("Hinder targets must be distinct")
            shared_segment = rng.randrange(SEGMENTS)
            for target in action.targets:
                if not 0 <= target < count or target == actor:
                    raise ValueError(f"Invalid target {target} for actor {actor}")
                segment = (shared_segment if hinder_segment_mode == "shared"
                           else rng.randrange(SEGMENTS))
                event = {"kind": "hinder", "actor": actor, "target": target,
                         "segment": segment,
                         "penalty": action.penalty}
                guarded = actions.get(target, RaceAction()).kind == "guard"
                event["guarded"] = guarded
                event["penalty_applied"] = action.penalty * (
                    1 - guard_absorption if guarded else 1
                )
                event["status"] = (
                    "reduced" if guarded and guard_absorption > 0 else "success"
                )
                modifiers[target][segment] -= event["penalty_applied"]
                events.append(event)
                # По старым правилам защита ослабляет каждую атаку,
                # а остаточные штрафы на одном участке складываются.
    return modifiers, events


def initial_nitro(count: int) -> int:
    """Стартовый запас каждого: пять при семи и семь при двенадцати."""
    return (count + 1) // 2 + 1


def resolve_nitro(
        count: int, actions: Mapping[int, RaceAction], seed: int,
) -> tuple[list[int], list[dict]]:
    """Перенести нитро по парам и вернуть запасы и закрытый журнал.

    Защищённый источник заменяется запасом отправителя, защищённый
    получатель — самим отправителем. При нехватке нитро у источника
    отправитель также платит из своего запаса. Конкурирующие заявки
    разрешаются в воспроизводимом порядке по seed, а не по времени клика.
    Журнал нужен только внутри симуляции и не публикуется в чате.
    """
    if count < 2:
        raise ValueError("At least two racers required")
    reserve = [initial_nitro(count)] * count
    requests = []
    for actor, action in actions.items():
        if not 0 <= actor < count or action.kind != "nitro":
            raise ValueError("Invalid nitro action")
        if action.plan not in ("early", "steady", "late"):
            raise ValueError("Invalid nitro plan")
        if len(action.guards) != len(set(action.guards)):
            raise ValueError("Duplicate guards")
        if len(action.guards) > min(5, max(3, (count - 1) // 2)):
            raise ValueError("Too many guards")
        if any(not 0 <= guard < count or guard == actor for guard in action.guards):
            raise ValueError("Invalid guard")
        if len(action.transfers) > min(5, max(3, (count - 1) // 2)):
            raise ValueError("Too many transfers")
        sources, recipients = zip(*action.transfers) if action.transfers else ((), ())
        if len(set(sources)) != len(sources) or len(set(recipients)) != len(recipients):
            raise ValueError("Transfer participants must be distinct per role")
        for source, recipient in action.transfers:
            if (source == actor or recipient == actor or source == recipient
                    or not 0 <= source < count or not 0 <= recipient < count):
                raise ValueError("Invalid transfer")
            requests.append((actor, source, recipient))

    rng = random.Random(seed ^ 0xA170)
    rng.shuffle(requests)
    events = []
    # Переводим по единице: ни долга, ни созданного «из воздуха» нитро.
    for actor, source, recipient in requests:
        paid_by = actor if actor in actions.get(source, RaceAction()).guards else source
        if reserve[paid_by] == 0:
            paid_by = actor
        delivered_to = (actor if actor in actions.get(recipient, RaceAction()).guards
                        else recipient)
        success = paid_by != delivered_to and reserve[paid_by] > 0
        if success:
            reserve[paid_by] -= 1
            reserve[delivered_to] += 1
        events.append({
            "kind": "transfer", "actor": actor, "source": source,
            "recipient": recipient, "paid_by": paid_by,
            "delivered_to": delivered_to, "status": "moved" if success else "empty",
        })
    assert sum(reserve) == count * initial_nitro(count)
    return reserve, events


def _nitro_schedule(charges: int, plan: str, frame_count: int) -> tuple[int, ...]:
    """Назначить кадры включения всех зарядов по выбранному плану."""
    # План меняет время расхода, но не количество доступных зарядов.
    if not charges:
        return ()
    bounds = {"early": (.05, .30), "steady": (.08, .65),
              "late": (.34, .68)}[plan]
    start, end = (round(frame_count * fraction) for fraction in bounds)
    if charges == 1:
        return ((start + end) // 2,)
    return tuple(round(start + (end - start) * i / (charges - 1))
                 for i in range(charges))


def _resolve_nitro_race(
        players, wheels, forecast, actions, seed, frame_count,
        track_distance, car_width, finish_margin, fee,
) -> RaceSimulationResult:
    """Рассчитать новую гонку: нитро, погодные участки и скорость по кадрам."""
    count = len(players)
    nitro, events = resolve_nitro(count, actions, seed)
    weather = _weather(random.Random(seed ^ 0xFEED), list(wheels), forecast)
    pulses = [_nitro_schedule(nitro[i], actions.get(i, RaceAction()).plan, frame_count)
              for i in range(count)]
    spans, finish_frames, positions = [], [], []
    threshold = track_distance - finish_margin
    base_speed = (track_distance + car_width) / frame_count
    # Фиксированное влияние шин заменяет старый индивидуальный разброс.
    tire_bonus = ((.08, .02, .02), (.02, .18, -.03), (.03, -.03, .16))
    for racer, tire in enumerate(wheels):
        position = 0.0
        racer_spans = []
        finished = None
        last_speed = None
        for frame in range(frame_count):
            segment = min(SEGMENTS - 1, int(SEGMENTS * position // track_distance))
            active = any(start <= frame < start + NITRO_PULSE_FRAMES
                         for start in pulses[racer])
            speed = (base_speed * (1 + tire_bonus[tire][weather[segment]])
                     * (1 + NITRO_SPEED_BONUS
                        * NITRO_WEATHER_MULTIPLIERS[weather[segment]]
                        if active else 1))
            if speed != last_speed:
                racer_spans.append(SpeedSpan(frame, position, speed))
                last_speed = speed
            position += speed
            if position >= threshold:
                finished = frame
                break
        spans.append(racer_spans)
        finish_frames.append(finished)
        positions.append(position)
    winners = sorted(range(count), key=lambda i: (
        finish_frames[i] if finish_frames[i] is not None else frame_count,
        -positions[i], i,
    ))
    return RaceSimulationResult(
        winners=winners, weather_segments=weather, spans=spans, events=events,
        prizes=allocate_prizes(count, fee), finish_frames=finish_frames,
        forecast=forecast, wheels=list(wheels), seed=seed, frame_count=frame_count,
        nitro=nitro, nitro_pulses=pulses,
    )


def resolve_race_simulation(
        players: Sequence[object],
        wheels: Sequence[int],
        weather_forecast: Mapping[str, Sequence[int]] | None,
        actions: Mapping[int, RaceAction] | None,
        seed: int,
        *,
        frame_count: int = 400,
        track_distance: float = 1700.0,
        car_width: float = 100.0,
        finish_margin: float = 10.0,
        guard_absorption: float = GUARD_ABSORPTION,
        hinder_segment_mode: str = "shared",
        fee: int = RACE_ENTRY_FEE,
) -> RaceSimulationResult:
    """Рассчитать заезд без графики; участники в действиях заданы индексами.

    Новые действия направляются в расчёт нитро. Старые действия сохраняют
    отдельные потоки случайности для сравнения стратегий при одном seed.
    """
    count = len(players)
    if count < 2 or len(wheels) != count or any(t not in (0, 1, 2) for t in wheels):
        raise ValueError("Provide at least two players and one valid tire per player")
    if frame_count <= 0 or track_distance <= finish_margin or car_width <= 0:
        raise ValueError("Invalid track dimensions or frame count")
    if hinder_segment_mode not in ("shared", "independent"):
        raise ValueError("Invalid segment mode")
    if not 0 <= guard_absorption < 1:
        raise ValueError("Guard absorption must be between 0 (inclusive) and 1 (exclusive)")
    if weather_forecast is None:
        weather_forecast = generate_forecast(seed)
    forecast = {str(i): list(weather_forecast[str(i)]) for i in (1, 2)}
    if any(len(values) != 3 or any(v < 0 for v in values) or sum(values) <= 0
           for values in forecast.values()):
        raise ValueError("Forecast weights must be three nonnegative values with a positive sum")
    weather = _weather(random.Random(seed ^ 0xFEED), list(wheels), forecast)
    if actions and all(action.kind == "nitro" for action in actions.values()):
        return _resolve_nitro_race(
            players, wheels, forecast, actions, seed, frame_count,
            track_distance, car_width, finish_margin, fee,
        )
    modifiers, events = _resolve_actions(
        random.Random(seed ^ 0xAC710), count, actions or {},
        guard_absorption=guard_absorption, hinder_segment_mode=hinder_segment_mode,
    )

    spans: list[list[SpeedSpan]] = []
    finish_frames: list[int | None] = []
    final_positions: list[float] = []
    threshold = track_distance - finish_margin
    initial_speed = (track_distance + car_width) / frame_count
    for racer, tire in enumerate(wheels):
        rng = random.Random((seed ^ 0x5EED) + racer * 1_000_003)
        position, frame, factor = 0.0, -1, 1.0
        racer_spans = [SpeedSpan(-1, 0.0, initial_speed)]
        # В старой анимации первый кадр идёт с базовой скоростью;
        # затем выбирается прибавка от шин и погоды первого участка.
        position += initial_speed
        frame += 1
        segment = 0
        lo, hi = SPEED_RANGES[weather[segment]][tire]
        weather_bonus = rng.uniform(lo, hi)
        factor += segment * rng.uniform(0, .02)
        speed = initial_speed * max(
            MIN_SPEED_FACTOR,
            factor + weather_bonus + modifiers[racer][segment],
        )
        racer_spans.append(SpeedSpan(frame, position, speed))
        while position < threshold and frame < frame_count - 1:
            boundary = min((segment + 1) * track_distance / SEGMENTS, threshold)
            steps = max(1, math.ceil((boundary - position) / speed - 1e-12))
            steps = min(steps, frame_count - 1 - frame)
            position += steps * speed
            frame += steps
            if position >= threshold or frame >= frame_count - 1:
                break
            segment = min(SEGMENTS - 1, int(SEGMENTS * position // track_distance))
            lo, hi = SPEED_RANGES[weather[segment]][tire]
            weather_bonus = rng.uniform(lo, hi)
            factor += segment * rng.uniform(0, .02)
            speed = initial_speed * max(
                MIN_SPEED_FACTOR,
                factor + weather_bonus + modifiers[racer][segment],
            )
            racer_spans.append(SpeedSpan(frame, position, speed))
        spans.append(racer_spans)
        finish_frames.append(frame if position >= threshold else None)
        final_positions.append(position)

    winners = sorted(
        range(count),
        key=lambda racer: (
            finish_frames[racer] if finish_frames[racer] is not None else frame_count,
            -final_positions[racer],
            racer,
        ),
    )
    return RaceSimulationResult(
        winners=winners, weather_segments=weather, spans=spans, events=events,
        prizes=allocate_prizes(count, fee), finish_frames=finish_frames,
        forecast=forecast, wheels=list(wheels), seed=seed, frame_count=frame_count,
    )
