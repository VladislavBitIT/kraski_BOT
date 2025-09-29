"""Minimal aiohttp stub for testing purposes."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any


class ClientSession:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError("aiohttp ClientSession is not available in this environment")


class ClientResponseError(RuntimeError):
    pass
