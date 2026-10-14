"""Monte Carlo comparison of racing cards, without rendering GIF/MP4 files.

Run from the repository root:
    python scripts/race_strategy_simulation.py --runs 100000 --players 8,10,12 \
        --strategies all --output simulation_results

Each scenario uses the production race resolver and common trial seeds.  The
"strongest" target policy is an optimistic information bound: tire choices are
private in the proposed game, so a real player cannot identify these targets
with certainty.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.race_simulation import (  # noqa: E402
    BOOST_BONUS, HINDER_PENALTY, HINDER_TARGETS, RACE_ENTRY_FEE,
    RACE_RULES_VERSION, SEGMENTS, SPEED_RANGES, RaceAction,
    generate_forecast, resolve_race_simulation,
)

DEFAULT_STRATEGIES = (
    "neutral", "boost_5", "guard",
    "hinder_1_10", "hinder_3_10", "hinder_4_10", "hinder_5_10",
    "hinder_3_15", "hinder_4_15", "hinder_5_15",
)
POPULATIONS = {
    "neutral": (0, 0, 0),
    "mix40": (40, 40, 20),
    "mix60boost": (60, 20, 20),
    "mix60hinder": (20, 60, 20),
    "equal": (1, 1, 1),
    "all_boost": (1, 0, 0),
    "all_hinder": (0, 1, 0),
    "all_guard": (0, 0, 1),
}
CSV_FIELDS = (
    "players", "strategy", "target_policy", "population", "guard_mode",
    "segment_mode", "runs", "mean_place", "median_place", "win_rate",
    "top3_rate", "prize_rate", "mean_prize", "median_prize", "min_prize",
    "max_prize", "successful_hinders", "blocked_hinders", "blocked_incoming",
    "affected_targets",
)


def strategy_action(strategy: str) -> RaceAction:
    if strategy == "neutral":
        return RaceAction()
    if strategy == "guard":
        return RaceAction(kind="guard")
    if strategy.startswith("boost_"):
        return RaceAction(kind="boost", bonus=int(strategy.split("_")[1]) / 100)
    if strategy.startswith("hinder_"):
        _, targets, penalty = strategy.split("_")
        return RaceAction(kind="hinder", targets=tuple(range(int(targets))),
                          penalty=int(penalty) / 100)
    raise ValueError(f"Unknown strategy: {strategy}")


def expected_strength(tire: int, forecast: dict[str, list[int]]) -> float:
    """Expected tire bonus from *forecast*, not secretly rolled weather."""
    return sum(
        sum(weight * sum(SPEED_RANGES[weather][tire]) / 2
            for weather, weight in enumerate(forecast[str(segment)]))
        / sum(forecast[str(segment)])
        for segment in (1, 2)
    )


def pick_targets(
        actor: int, count: int, wheels: list[int], forecast: dict[str, list[int]],
        policy: str, rng: random.Random,
) -> tuple[int, ...]:
    candidates = [target for target in range(len(wheels)) if target != actor]
    count = min(count, len(candidates))
    if policy == "random":
        return tuple(rng.sample(candidates, count))
    ranked = sorted(candidates, key=lambda target: (
        -expected_strength(wheels[target], forecast), target
    ))
    if policy == "strongest":
        return tuple(ranked[:count])
    if policy == "upper_half":
        # The pool must still hold the requested number of distinct targets.
        pool = ranked[:max(count, math.ceil(len(ranked) / 2))]
        return tuple(rng.sample(pool, count))
    raise ValueError(f"Unknown target policy: {policy}")


def build_actions(
        focal_strategy: str, n: int, wheels: list[int], forecast: dict[str, list[int]],
        policy: str, population: str, rng: random.Random,
        opponent_hinder_targets: int, opponent_hinder_penalty: float,
        opponent_boost: float,
        scale_targets: bool = False,
) -> dict[int, RaceAction]:
    actions = {}
    target_limit = max(1, (n - 1) // 2) if scale_targets else n - 1
    boost_weight, hinder_weight, guard_weight = POPULATIONS[population]
    for actor in range(1, n):
        if population == "neutral":
            continue
        kind = rng.choices(
            ("boost", "hinder", "guard"),
            weights=(boost_weight, hinder_weight, guard_weight),
            k=1,
        )[0]
        if kind == "boost":
            actions[actor] = RaceAction(kind="boost", bonus=opponent_boost)
        elif kind == "guard":
            actions[actor] = RaceAction(kind="guard")
        else:
            targets = pick_targets(
                actor, min(opponent_hinder_targets, target_limit),
                wheels, forecast, policy, rng,
            )
            actions[actor] = RaceAction(
                kind="hinder", targets=targets, penalty=opponent_hinder_penalty,
            )
    focal = strategy_action(focal_strategy)
    if focal.kind == "hinder":
        focal = RaceAction(
            kind="hinder",
            targets=pick_targets(
                0, min(len(focal.targets), target_limit),
                wheels, forecast, policy, rng,
            ),
            penalty=focal.penalty,
        )
    actions[0] = focal
    return actions


def _counts(values: Counter, runs: int) -> float:
    return sum(value * count for value, count in values.items()) / runs


def run_scenario(
        *,
        n: int, strategy: str, policy: str, population: str,
        guard_mode: str, segment_mode: str, runs: int, seed: int,
        opponent_hinder_targets: int, opponent_hinder_penalty: float,
        opponent_boost: float, sample_races: int = 3,
        scale_targets: bool = False,
) -> tuple[dict, dict]:
    ranks: Counter = Counter()
    prizes: Counter = Counter()
    weathers: Counter = Counter()
    tires: Counter = Counter()
    statuses: Counter = Counter()
    samples = []
    for trial in range(runs):
        # Trial seeds do not depend on strategy or target policy. This is
        # common-random-numbers comparison rather than separate random races.
        race_seed = seed + n * 1_000_003 + trial
        wheels_rng = random.Random(race_seed ^ 0x77EE15)
        wheels = [wheels_rng.randrange(3) for _ in range(n)]
        forecast = generate_forecast(race_seed)
        actions = build_actions(
            strategy, n, wheels, forecast, policy, population,
            random.Random(race_seed ^ 0xAC710A5),
            opponent_hinder_targets, opponent_hinder_penalty, opponent_boost,
            scale_targets,
        )
        result = resolve_race_simulation(
            players=range(n), wheels=wheels, weather_forecast=forecast,
            actions=actions, seed=race_seed, guard_mode=guard_mode,
            hinder_segment_mode=segment_mode, fee=RACE_ENTRY_FEE,
        )
        place = result.winners.index(0) + 1
        prize = result.prizes.get(place, 0)
        ranks[place] += 1
        prizes[prize] += 1
        weathers["".join(map(str, result.weather_segments))] += 1
        tires["-".join(str(wheels.count(tire)) for tire in range(3))] += 1
        for event in result.events:
            if event["kind"] == "hinder":
                if event["actor"] == 0:
                    statuses[f"outgoing_{event['status']}"] += 1
                if event["target"] == 0 and event["status"] == "blocked":
                    statuses["blocked_incoming"] += 1
                if event["actor"] == 0 and event["status"] == "success":
                    statuses[f"affected_{event['target']}"] += 1
        if len(samples) < sample_races:
            samples.append({
                "trial": trial, "seed": race_seed, "forecast": forecast,
                "weather": result.weather_segments, "wheels": wheels,
                "actions": {
                    str(actor): {
                        "kind": action.kind, "targets": action.targets,
                        "bonus": action.bonus if action.kind == "boost" else None,
                        "penalty": action.penalty if action.kind == "hinder" else None,
                    }
                    for actor, action in actions.items()
                },
                "order": result.winners, "place": place, "prize": prize,
                "events": result.events,
            })
    summary = {
        "players": n, "strategy": strategy, "target_policy": policy,
        "population": population, "guard_mode": guard_mode,
        "segment_mode": segment_mode, "runs": runs,
        "mean_place": _counts(ranks, runs),
        "median_place": median(sorted(place for place, count in ranks.items()
                                      for _ in range(count))),
        "win_rate": ranks[1] / runs,
        "top3_rate": sum(ranks[place] for place in (1, 2, 3)) / runs,
        "prize_rate": (runs - prizes[0]) / runs,
        "mean_prize": _counts(prizes, runs),
        "median_prize": median(sorted(prize for prize, count in prizes.items()
                                      for _ in range(count))),
        "min_prize": min(prizes), "max_prize": max(prizes),
        "successful_hinders": statuses["outgoing_success"] / runs,
        "blocked_hinders": statuses["outgoing_blocked"] / runs,
        "blocked_incoming": statuses["blocked_incoming"] / runs,
        "affected_targets": sum(
            value for key, value in statuses.items() if key.startswith("affected_")
        ) / runs,
    }
    detail = {
        "summary": summary,
        "rank_histogram": dict(sorted(ranks.items())),
        "prize_histogram": dict(sorted(prizes.items())),
        "weather_histogram": dict(sorted(weathers.items())),
        "tires_histogram": dict(sorted(tires.items())),
        "event_counts": dict(sorted(statuses.items())),
        "sample_races": samples,
    }
    return summary, detail


def _choices(value: str, allowed: set[str]) -> list[str]:
    choices = list(allowed) if value == "all" else value.split(",")
    if not choices or any(item not in allowed for item in choices):
        raise argparse.ArgumentTypeError(f"Choose from: {', '.join(sorted(allowed))}")
    return sorted(set(choices))


def assess_balance(rows: list[dict], reference_strategy: str = "boost_5") -> list[dict]:
    """Flag candidates per identical race size, opponents and target policy.

    The payout/win bounds are diagnostics, not an automatic rules decision:
    targeted sabotage and player enjoyment are not captured by these numbers.
    """
    reference = {
        (row["players"], row["target_policy"], row["population"],
         row["guard_mode"], row["segment_mode"]): row
        for row in rows if row["strategy"] == reference_strategy
    }
    assessments = []
    for row in rows:
        key = (row["players"], row["target_policy"], row["population"],
               row["guard_mode"], row["segment_mode"])
        baseline = reference.get(key)
        if baseline is None or row["strategy"] == reference_strategy:
            continue
        payout_ratio = row["mean_prize"] / baseline["mean_prize"]
        if row["win_rate"] and baseline["win_rate"]:
            win_ratio = max(
                row["win_rate"] / baseline["win_rate"],
                baseline["win_rate"] / row["win_rate"],
            )
        else:
            win_ratio = None
        assessments.append({
            "players": row["players"], "target_policy": row["target_policy"],
            "population": row["population"], "guard_mode": row["guard_mode"],
            "segment_mode": row["segment_mode"], "strategy": row["strategy"],
            "reference_strategy": reference_strategy,
            "payout_ratio": payout_ratio,
            "win_ratio": win_ratio,
            "within_numeric_bounds": (
                    .9 <= payout_ratio <= 1.1
                    and win_ratio is not None and win_ratio <= 1.5
            ),
        })
    return assessments


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=100000, help="trials per combination")
    parser.add_argument("--players", default="8,9,10,11,12", help="comma-separated counts")
    parser.add_argument("--strategies", default="all", help="all or comma-separated names")
    parser.add_argument("--seed", type=int, default=20261014)
    parser.add_argument("--boost-bonus", type=float, default=BOOST_BONUS)
    parser.add_argument("--hinder-targets", type=int, default=HINDER_TARGETS)
    parser.add_argument("--hinder-penalty", type=float, default=HINDER_PENALTY)
    parser.add_argument("--scale-targets", action="store_true",
                        help="cap target count at floor((players - 1) / 2)")
    parser.add_argument("--target-policy", default="random",
                        help="all, random, strongest, upper_half")
    parser.add_argument("--guard-mode", default="all", help="all, one, both")
    parser.add_argument("--segment-mode", default="shared",
                        help="shared, independent, both")
    parser.add_argument("--population", default="neutral",
                        help="neutral, mix40, mix60boost, mix60hinder, equal, "
                             "all_boost, all_hinder, all_guard, or all")
    parser.add_argument("--sample-races", type=int, default=3)
    parser.add_argument("--output", type=Path, default=Path("simulation_results"))
    args = parser.parse_args(argv)
    args.players = [int(value) for value in args.players.split(",")]
    if args.runs <= 0 or any(not 7 <= n <= 12 for n in args.players):
        parser.error("runs must be positive and player counts must be 7–12")
    if args.hinder_targets < 1 or not 0 < args.hinder_penalty < 1:
        parser.error("hinder targets must be positive; penalty must be between 0 and 1")
    if not 0 < args.boost_bonus < 1 or args.sample_races < 0:
        parser.error("boost bonus must be between 0 and 1; samples cannot be negative")
    if (not math.isfinite(args.hinder_penalty) or not math.isfinite(args.boost_bonus)
            or abs(round(args.hinder_penalty * 100) - args.hinder_penalty * 100) > 1e-8
            or abs(round(args.boost_bonus * 100) - args.boost_bonus * 100) > 1e-8):
        parser.error("bonus and penalty must be finite whole percentage points")
    args.policies = _choices(args.target_policy, {"random", "strongest", "upper_half"})
    if args.guard_mode not in ("all", "one", "both"):
        parser.error("guard-mode must be all, one, or both")
    args.guards = ["all", "one"] if args.guard_mode == "both" else [args.guard_mode]
    args.segments = _choices(
        "shared,independent" if args.segment_mode == "both" else args.segment_mode,
        {"shared", "independent"},
    )
    args.populations = _choices(args.population, set(POPULATIONS))
    custom_boost = f"boost_{round(args.boost_bonus * 100)}"
    custom_hinder = f"hinder_{args.hinder_targets}_{round(args.hinder_penalty * 100)}"
    available = set(DEFAULT_STRATEGIES) | {custom_boost, custom_hinder}
    args.selected_strategies = (
        list(dict.fromkeys((*DEFAULT_STRATEGIES, custom_boost, custom_hinder)))
        if args.strategies == "all" else _choices(args.strategies, available)
    )
    return args


def main(argv: list[str] | None = None) -> tuple[list[dict], dict]:
    args = parse_args(argv)
    started = datetime.now(timezone.utc)
    summaries, details = [], []
    for n in args.players:
        for population in args.populations:
            for guard in args.guards:
                for segment in args.segments:
                    for policy in args.policies:
                        for strategy in args.selected_strategies:
                            summary, detail = run_scenario(
                                n=n, strategy=strategy, policy=policy,
                                population=population, guard_mode=guard,
                                segment_mode=segment, runs=args.runs, seed=args.seed,
                                opponent_hinder_targets=args.hinder_targets,
                                opponent_hinder_penalty=args.hinder_penalty,
                                opponent_boost=args.boost_bonus,
                                sample_races=args.sample_races,
                                scale_targets=args.scale_targets,
                            )
                            summaries.append(summary)
                            details.append(detail)
                            print(
                                f"{n:2d} {population:12s} {policy:10s} "
                                f"{guard:3s}/{segment:11s} {strategy:14s} "
                                f"place={summary['mean_place']:.2f} "
                                f"win={summary['win_rate']:.1%} "
                                f"top3={summary['top3_rate']:.1%} "
                                f"prize={summary['mean_prize']:.2f}"
                            )
    report = {
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "rules": {
            "version": RACE_RULES_VERSION,
            "entry_fee": RACE_ENTRY_FEE, "boost_bonus": args.boost_bonus,
            "hinder_penalty": args.hinder_penalty,
            "hinder_targets": args.hinder_targets, "segments": SEGMENTS,
            "guard_mode": args.guards[0] if len(args.guards) == 1 else "both",
            "scale_targets": args.scale_targets,
            "guard_modes": args.guards, "segment_modes": args.segments,
            "speed_ranges": SPEED_RANGES,
            "strategy_parameters": {
                strategy: {
                    "bonus": action.bonus if action.kind == "boost" else None,
                    "penalty": action.penalty if action.kind == "hinder" else None,
                    "targets": len(action.targets) if action.kind == "hinder" else 0,
                }
                for strategy in args.selected_strategies
                for action in (strategy_action(strategy),)
            },
            "target_policy_note": (
                "strongest/upper_half use forecast and private tire knowledge "
                "as an optimistic upper bound, not information available in the bot"
            ),
            "stack_cap": "one successful incoming hinder per racer",
        },
        "seed": args.seed, "runs_per_combination": args.runs,
        "scenarios": details,
        "balance_assessment": assess_balance(summaries),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.with_suffix(".csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(summaries)
    with args.output.with_suffix(".json").open("w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    return summaries, report


if __name__ == "__main__":
    main()
