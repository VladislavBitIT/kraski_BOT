"""Helpers for user facing formatting."""
from __future__ import annotations

from typing import Dict


def format_packages(packages: Dict[float, int], unit: str) -> str:
    parts = []
    for size, count in sorted(packages.items(), key=lambda item: (-item[1], -item[0])):
        size_str = f"{size:g} {unit}"
        parts.append(f"{count}×{size_str}")
    return " и ".join(parts)


def format_currency(value: float) -> str:
    return f"{int(round(value)):,}".replace(",", " ")


def format_percentage(value: float) -> str:
    return f"{int(value * 100)}%"
