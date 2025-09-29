"""Deep link helpers for the bot."""
from __future__ import annotations

import base64
from typing import Optional


PREFIX = "paint_"


def encode_payload(sku: str) -> str:
    payload = base64.urlsafe_b64encode(sku.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{PREFIX}{payload}"


def decode_payload(payload: Optional[str]) -> Optional[str]:
    if not payload or not payload.startswith(PREFIX):
        return None
    encoded = payload[len(PREFIX) :]
    padding = "=" * (-len(encoded) % 4)
    try:
        return base64.urlsafe_b64decode(encoded + padding).decode("utf-8")
    except Exception:
        return None
