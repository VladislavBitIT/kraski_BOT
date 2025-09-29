"""Utility helpers for calculating optimal packaging combinations."""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from math import ceil
from typing import Dict, Iterable, List, Tuple


@dataclass(slots=True)
class CombinationResult:
    packages: Dict[float, int]
    supplied_amount: float
    overfill: float
    total_price: float

    def as_pairs(self) -> List[Tuple[float, int]]:
        return list(self.packages.items())


def greedy_initial(target: float, sizes: Iterable[float]) -> Dict[float, int]:
    """Return a greedy combination that reaches the target value."""

    remaining = target
    result: Dict[float, int] = {}
    for size in sorted(sizes, reverse=True):
        if remaining <= 0:
            break
        count = int(ceil(remaining / size)) if size else 0
        if count:
            result[size] = count
            remaining -= size * count
    if remaining > 0 and sizes:
        smallest = min(sizes)
        result[smallest] = result.get(smallest, 0) + 1
    return result


def calculate_overfill(target: float, packages: Dict[float, int]) -> float:
    supplied = sum(size * count for size, count in packages.items())
    return max(0.0, supplied - target)


def optimise_combination(
    target: float,
    sizes: List[float],
    prices: Dict[float, float],
    base: Dict[float, int],
) -> CombinationResult:
    """Try to optimise greedy combination by local replacements."""

    best = CombinationResult(
        packages=dict(base),
        supplied_amount=sum(size * count for size, count in base.items()),
        overfill=calculate_overfill(target, base),
        total_price=sum(prices[size] * count for size, count in base.items()),
    )

    # Iterate over limited search space by varying counts up to +2/-2
    search_space: List[List[int]] = []
    for size in sizes:
        count = base.get(size, 0)
        search_space.append(list(range(max(0, count - 2), count + 3)))

    for counts in product(*search_space):
        packages = {size: count for size, count in zip(sizes, counts) if count > 0}
        if not packages:
            continue
        supplied = sum(size * count for size, count in packages.items())
        if supplied < target:
            continue
        overfill = supplied - target
        price = sum(prices[size] * count for size, count in packages.items())
        if (overfill < best.overfill) or (
            overfill == best.overfill and price < best.total_price
        ):
            best = CombinationResult(packages, supplied, overfill, price)
    return best


def pick_optimal_combination(
    target: float,
    sizes: Iterable[float],
    prices: Dict[float, float],
) -> CombinationResult:
    """Return the best combination of packaging sizes to cover the target amount."""

    sizes = sorted(set(float(size) for size in sizes if float(size) > 0), reverse=True)
    if not sizes:
        raise ValueError("No packaging sizes provided")
    missing = [size for size in sizes if size not in prices]
    if missing:
        raise ValueError(f"Missing prices for packaging sizes: {missing}")

    greedy = greedy_initial(target, sizes)
    return optimise_combination(target, sizes, prices, greedy)
