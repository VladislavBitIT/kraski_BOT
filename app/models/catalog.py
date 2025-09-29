"""Data models for catalog entities used by the paint calculator bot."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(slots=True)
class PackagingPrice:
    """Price information for a single packaging size."""

    size: float
    price: float


@dataclass(slots=True)
class Paint:
    """Represents a paint product that can be selected inside the bot."""

    sku: str
    brand: str
    series: str
    category: str
    name: str
    url: Optional[str]
    unit: str
    packagings: List[float]
    prices: Dict[float, float]
    consumption_min: Optional[float]
    consumption_max: Optional[float]
    density_kg_l: Optional[float] = None

    def get_consumption_average(self) -> float:
        """Return average consumption (g/m²) based on min/max values."""

        values = [v for v in (self.consumption_min, self.consumption_max) if v]
        if not values:
            raise ValueError(f"Consumption values are missing for paint {self.sku}")
        return sum(values) / len(values)

    def available_packagings(self) -> List[float]:
        """Return the list of packagings for which price is defined."""

        return [size for size in self.packagings if size in self.prices]


@dataclass(slots=True)
class Primer:
    """Represents a primer product that can be optionally calculated."""

    code: str
    name: str
    unit: str
    packagings: List[float]
    prices: Dict[float, float]
    consumption_min: Optional[float]
    consumption_max: Optional[float]
    default_layers: int = 1
    density_kg_l: Optional[float] = None

    def get_consumption_average(self) -> float:
        values = [v for v in (self.consumption_min, self.consumption_max) if v]
        if not values:
            raise ValueError(f"Consumption values are missing for primer {self.code}")
        return sum(values) / len(values)

    def available_packagings(self) -> List[float]:
        return [size for size in self.packagings if size in self.prices]


@dataclass(slots=True)
class CatalogData:
    """Container with categories, paints and primers loaded from Excel."""

    categories: List[str] = field(default_factory=list)
    paints: List[Paint] = field(default_factory=list)
    primers: List[Primer] = field(default_factory=list)

    def get_paint_by_sku(self, sku: str) -> Optional[Paint]:
        sku_lower = sku.lower()
        for paint in self.paints:
            if paint.sku.lower() == sku_lower:
                return paint
        return None

    def get_primer_by_code(self, code: str) -> Optional[Primer]:
        code_lower = code.lower()
        for primer in self.primers:
            if primer.code.lower() == code_lower:
                return primer
        return None
