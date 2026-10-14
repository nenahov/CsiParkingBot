"""Pure race rules shared by the renderer and the balance simulator.

Positions are advanced in runs of equal speed rather than one image frame at a
time.  A speed is resampled on entry to each of the three track segments, as
in the original animation.  No PIL, database or Telegram objects are needed.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Mapping, Sequence

RACE_ENTRY_FEE = 50
RACE_RULES_VERSION = "risk-intrigue-2"
BOOST_BONUS = 0.05
HINDER_TARGETS = 5
HINDER_PENALTY = 0.10
PLACE_WEIGHTS = (35, 25, 17, 12, 8)
SEGMENTS = 3
# Indexed by weather (cloud, rain, sun), then tire (universal, rain, slick).
SPEED_RANGES = (
    ((.15, .40), (.00, .10), (.05, .20)),
    ((.05, .20), (.40, .80), (.00, .05)),
    ((.05, .20), (.00, .05), (.30, .70)),
)


@dataclass(frozen=True)
class RaceAction:
    kind: str = "neutral"
    targets: tuple[int, ...] = ()
    bonus: float = BOOST_BONUS
    penalty: float = HINDER_PENALTY


def action_to_dict(action: RaceAction) -> dict:
    return {
        "kind": action.kind,
        "targets": list(action.targets),
        "bonus": action.bonus,
        "penalty": action.penalty,
    }


def action_from_dict(data: dict) -> RaceAction:
    return RaceAction(
        kind=data.get("kind", "neutral"),
        targets=tuple(int(target) for target in data.get("targets", ())),
        bonus=float(data.get("bonus", BOOST_BONUS)),
        penalty=float(data.get("penalty", HINDER_PENALTY)),
    )


@dataclass(frozen=True)
class SpeedSpan:
    frame: int
    position: float
    speed: float


@dataclass
class RaceSimulationResult:
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

    def position_at(self, racer: int, frame: int) -> float:
        spans = self.spans[racer]
        # At most five spans per racer; a linear scan is cheaper than building
        # a list of 400 positions for each trial in a Monte Carlo run.
        span = spans[0]
        for candidate in spans[1:]:
            if candidate.frame > frame:
                break
            span = candidate
        return span.position + (frame - span.frame) * span.speed


def allocate_prizes(players_count: int, fee: int = RACE_ENTRY_FEE) -> dict[int, int]:
    """Return payouts by *one-based place*, conserving the entry-fee pool."""
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
    result = {}
    for number in (1, 2):
        cloud = rng.randint(0, 10)
        rain = rng.randint(0, 10 - cloud)
        result[str(number)] = [cloud, rain, 10 - cloud - rain]
    return result


def generate_forecast(seed: int) -> dict[str, list[int]]:
    """Generate the two-segment forecast used by a seeded simulated race."""
    return _forecast(random.Random(seed ^ 0x71A5EED))


def _weather(
        rng: random.Random, wheels: Sequence[int], forecast: Mapping[str, Sequence[int]]
) -> list[int]:
    result = [rng.choices((0, 1, 2), weights=forecast[str(i)], k=1)[0]
              for i in (1, 2)]
    counts = [wheels.count(tire) for tire in range(3)]
    least = min(counts)
    # Include tire types absent from the grid: their count is zero.
    result.append(rng.choice([tire for tire, count in enumerate(counts) if count == least]))
    return result


def _resolve_actions(
        rng: random.Random, count: int, actions: Mapping[int, RaceAction],
        *, guard_mode: str, hinder_segment_mode: str,
) -> tuple[list[list[float]], list[dict]]:
    modifiers = [[0.0] * SEGMENTS for _ in range(count)]
    incoming: list[list[dict]] = [[] for _ in range(count)]
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
                         "segment": segment, "status": "pending",
                         "penalty": action.penalty}
                events.append(event)
                incoming[target].append(event)
    for target, attacks in enumerate(incoming):
        if not attacks:
            continue
        rng.shuffle(attacks)  # no advantage from player/iteration order
        if actions.get(target, RaceAction()).kind == "guard":
            protected = attacks if guard_mode == "all" else attacks[:1]
            for attack in protected:
                attack["status"] = "blocked"
        for attack in attacks:
            if attack["status"] == "pending":
                attack["status"] = "success"
                modifiers[target][attack["segment"]] -= attack["penalty"]
                break
        for attack in attacks:
            if attack["status"] == "pending":
                attack["status"] = "stack_cap"
    return modifiers, events


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
        guard_mode: str = "all",
        hinder_segment_mode: str = "shared",
        fee: int = RACE_ENTRY_FEE,
) -> RaceSimulationResult:
    """Resolve one race, without rendering it; actions and targets use lane indexes.

    Independent RNG streams for environment, actions and speed keep the same
    baseline when strategies are compared with a common seed.
    """
    count = len(players)
    if count < 2 or len(wheels) != count or any(t not in (0, 1, 2) for t in wheels):
        raise ValueError("Provide at least two players and one valid tire per player")
    if frame_count <= 0 or track_distance <= finish_margin or car_width <= 0:
        raise ValueError("Invalid track dimensions or frame count")
    if guard_mode not in ("all", "one") or hinder_segment_mode not in ("shared", "independent"):
        raise ValueError("Invalid guard or segment mode")
    if weather_forecast is None:
        weather_forecast = generate_forecast(seed)
    forecast = {str(i): list(weather_forecast[str(i)]) for i in (1, 2)}
    if any(len(values) != 3 or any(v < 0 for v in values) or sum(values) <= 0
           for values in forecast.values()):
        raise ValueError("Forecast weights must be three nonnegative values with a positive sum")
    weather = _weather(random.Random(seed ^ 0xFEED), list(wheels), forecast)
    modifiers, events = _resolve_actions(
        random.Random(seed ^ 0xAC710), count, actions or {},
        guard_mode=guard_mode, hinder_segment_mode=hinder_segment_mode,
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
        # The first frame advances at the base speed. Only then does the
        # original animation sample the tire/weather bonus for segment zero.
        position += initial_speed
        frame += 1
        segment = 0
        lo, hi = SPEED_RANGES[weather[segment]][tire]
        weather_bonus = rng.uniform(lo, hi)
        factor += segment * rng.uniform(0, .02)
        speed = (track_distance + car_width) * (
                factor + weather_bonus + modifiers[racer][segment]
        ) / frame_count
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
            speed = (track_distance + car_width) * (
                    factor + weather_bonus + modifiers[racer][segment]
            ) / frame_count
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
