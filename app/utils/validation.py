"""Validation helpers used across handlers."""
from __future__ import annotations

import re
from typing import Optional

PHONE_PATTERN = re.compile(r"^\+?\d[\d\-\s\(\)]{7,}$")


def parse_float(value: str) -> Optional[float]:
    try:
        cleaned = value.replace(",", ".").strip()
        return float(cleaned)
    except (ValueError, AttributeError):
        return None


def validate_phone(value: str) -> bool:
    return bool(PHONE_PATTERN.match(value.strip())) if value else False
