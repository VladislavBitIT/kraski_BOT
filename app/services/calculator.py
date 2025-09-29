"""Calculation logic for paint and primer consumption."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional

from app.models.catalog import Paint, Primer
from app.utils.pack_combiner import pick_optimal_combination


@dataclass(slots=True)
class CalculationBreakdown:
    unit: str
    required_amount: float
    supplied_amount: float
    overfill_amount: float
    extra_area: float
    packages: Dict[float, int]
    total_price: float


@dataclass(slots=True)
class CalculationResult:
    paint: CalculationBreakdown
    primers: Dict[str, CalculationBreakdown]
    total_price: float


TOOL_FACTORS = {
    "roller": 1.0,
    "sprayer": 1.3,
}

SURFACE_FACTORS = {
    ("roller", "wall"): 1.0,
    ("roller", "ceiling"): 1.0,
    ("sprayer", "wall"): 1.0,
    ("sprayer", "ceiling"): 1.2,
}


def _ensure_density(unit: str, density: Optional[float], item_name: str) -> float:
    if unit == "l":
        if not density:
            raise ValueError(
                f"Density_kg_l is required for liter based item '{item_name}'"
            )
        return float(density)
    return 1.0


def _calc_consumption(cons_min: Optional[float], cons_max: Optional[float]) -> float:
    values = [v for v in (cons_min, cons_max) if v]
    if not values:
        raise ValueError("Consumption data is missing")
    return sum(values) / len(values)


def calculate_paint(
    paint: Paint,
    area_m2: float,
    tool: str,
    surface: str,
    reserve: float,
) -> CalculationBreakdown:
    layers = 2
    tool_factor = TOOL_FACTORS[tool]
    surface_factor = SURFACE_FACTORS[(tool, surface)]

    base_consumption = _calc_consumption(paint.consumption_min, paint.consumption_max)
    adjusted_consumption = base_consumption * tool_factor * surface_factor
    required_grams = area_m2 * layers * adjusted_consumption * (1 + reserve)

    density_factor = _ensure_density(paint.unit, paint.density_kg_l, paint.sku)
    if paint.unit == "kg":
        required_units = required_grams / 1000
        supplied_to_grams = 1000
    else:
        required_units = (required_grams / 1000) / density_factor
        supplied_to_grams = density_factor * 1000

    combination = pick_optimal_combination(
        required_units, paint.available_packagings(), paint.prices
    )

    supplied_units = combination.supplied_amount
    supplied_grams = supplied_units * supplied_to_grams
    overfill_units = combination.overfill
    extra_area = max(
        0.0, (supplied_grams - required_grams) / (adjusted_consumption * layers)
    )

    return CalculationBreakdown(
        unit=paint.unit,
        required_amount=required_units,
        supplied_amount=supplied_units,
        overfill_amount=overfill_units,
        extra_area=extra_area,
        packages=combination.packages,
        total_price=combination.total_price,
    )


def calculate_primer(primer: Primer, area_m2: float) -> CalculationBreakdown:
    layers = primer.default_layers or 1
    base_consumption = _calc_consumption(primer.consumption_min, primer.consumption_max)
    required_grams = area_m2 * layers * base_consumption
    density_factor = _ensure_density(primer.unit, primer.density_kg_l, primer.code)

    if primer.unit == "kg":
        required_units = required_grams / 1000
        supplied_to_grams = 1000
    else:
        required_units = (required_grams / 1000) / density_factor
        supplied_to_grams = density_factor * 1000

    combination = pick_optimal_combination(
        required_units, primer.available_packagings(), primer.prices
    )
    supplied_units = combination.supplied_amount
    supplied_grams = supplied_units * supplied_to_grams
    extra_area = max(
        0.0, (supplied_grams - required_grams) / (base_consumption * layers)
    )

    return CalculationBreakdown(
        unit=primer.unit,
        required_amount=required_units,
        supplied_amount=supplied_units,
        overfill_amount=combination.overfill,
        extra_area=extra_area,
        packages=combination.packages,
        total_price=combination.total_price,
    )


def calculate_total(
    paint: Paint,
    primers: Iterable[Primer],
    area_m2: float,
    tool: str,
    surface: str,
    reserve: float,
) -> CalculationResult:
    paint_breakdown = calculate_paint(paint, area_m2, tool, surface, reserve)
    primer_breakdowns: Dict[str, CalculationBreakdown] = {}
    for primer in primers:
        primer_breakdowns[primer.code] = calculate_primer(primer, area_m2)

    total = paint_breakdown.total_price + sum(
        breakdown.total_price for breakdown in primer_breakdowns.values()
    )
    return CalculationResult(paint_breakdown, primer_breakdowns, total)
