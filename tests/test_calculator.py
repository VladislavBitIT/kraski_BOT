from __future__ import annotations

from app.models.catalog import Paint, Primer
from app.services.calculator import (
    SURFACE_FACTORS,
    TOOL_FACTORS,
    calculate_paint,
    calculate_total,
)
from app.utils.pack_combiner import pick_optimal_combination


def make_paint() -> Paint:
    return Paint(
        sku="BUTTERFLY",
        brand="DERUFA",
        series="Butterfly",
        category="Интерьерные",
        name="Butterfly",
        url=None,
        unit="kg",
        packagings=[7.0, 14.0],
        prices={7.0: 2090.0, 14.0: 3450.0},
        consumption_min=180.0,
        consumption_max=200.0,
    )


def make_primer(code: str) -> Primer:
    return Primer(
        code=code,
        name=code,
        unit="kg",
        packagings=[10.0],
        prices={10.0: 1500.0},
        consumption_min=100.0,
        consumption_max=120.0,
        default_layers=1,
    )


def test_tool_surface_factors():
    assert TOOL_FACTORS["roller"] == 1.0
    assert TOOL_FACTORS["sprayer"] == 1.3
    assert SURFACE_FACTORS[("sprayer", "ceiling")] == 1.2


def test_calculate_paint_basic():
    paint = make_paint()
    breakdown = calculate_paint(paint, area_m2=40.0, tool="roller", surface="wall", reserve=0.0)
    assert breakdown.packages[14.0] == 1
    assert breakdown.packages[7.0] == 1
    assert round(breakdown.extra_area, 1) >= 0


def test_pick_optimal_combination():
    result = pick_optimal_combination(10, [7, 3], {7: 1000, 3: 500})
    assert result.packages == {7.0: 1, 3.0: 1}


def test_calculate_total_with_primer():
    paint = make_paint()
    primer = make_primer("ACRYLGRUND")
    result = calculate_total(paint, [primer], 20.0, "roller", "wall", 0.0)
    assert "ACRYLGRUND" in result.primers
    assert result.total_price >= result.paint.total_price
