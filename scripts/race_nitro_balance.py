"""Воспроизводимая предварительная проверка баланса нитро-гонки.

Запуск из корня репозитория:
    python scripts/race_nitro_balance.py --runs 500

Сравнивает планы при случайных допустимых решениях игроков. Это
проверка на явные перекосы, а не поиск оптимальной человеческой стратегии.
"""

import argparse
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.race_simulation import (
    RaceAction, generate_forecast, initial_nitro, resolve_race_simulation,
)


def random_actions(count, rng):
    """Сгенерировать допустимые перевозки, защиты и планы для всех водителей."""
    limit = min(5, max(3, (count - 1) // 2))
    actions = {}
    for actor in range(count):
        others = [i for i in range(count) if i != actor]
        sources = rng.sample(others, limit)
        recipients = rng.sample(others, limit)
        # В одной паре источник и получатель не должны совпадать.
        for index, source in enumerate(sources):
            if recipients[index] == source:
                swap = next(
                    j for j in range(limit)
                    if j != index and recipients[j] != source
                    and recipients[index] != sources[j]
                )
                recipients[index], recipients[swap] = recipients[swap], recipients[index]
        actions[actor] = RaceAction(
            kind="nitro",
            transfers=tuple(zip(sources, recipients)),
            guards=tuple(rng.sample(others, limit)),
            plan=rng.choice(("early", "steady", "late")),
        )
    return actions


def main(argv=None):
    """Прогнать заезды и вывести долю побед, среднее место и запас нитро."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=500)
    parser.add_argument("--seed", type=int, default=20261026)
    args = parser.parse_args(argv)
    rng = random.Random(args.seed)
    for count in range(7, 13):
        summary = defaultdict(lambda: [0, 0, 0, 0])
        for _ in range(args.runs):
            seed = rng.randrange(2 ** 31)
            actions = random_actions(count, rng)
            wheels = [rng.randrange(3) for _ in range(count)]
            result = resolve_race_simulation(
                range(count), wheels, generate_forecast(seed), actions, seed,
            )
            assert sum(result.nitro) == count * initial_nitro(count)
            for place, actor in enumerate(result.winners, 1):
                row = summary[actions[actor].plan]
                row[0] += 1
                row[1] += place == 1
                row[2] += place
                row[3] += result.nitro[actor]
        print(f"{count} racers, {args.runs} races:")
        for plan, (entries, wins, rank, nitro) in sorted(summary.items()):
            print(f"  {plan:6} win {wins / entries:.1%}, "
                  f"mean place {rank / entries:.2f}, "
                  f"mean nitro {nitro / entries:.2f}")


if __name__ == "__main__":
    main()
