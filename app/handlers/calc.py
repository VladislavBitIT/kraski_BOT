"""Skeleton handlers for calculator flow.

The detailed business logic is encapsulated in :mod:`app.services.calculator`.
The router exposes callbacks that can be connected to Telegram events in the
future. The implementation focuses on testable backend logic, while providing a
clear structure for FSM driven conversations.
"""
from __future__ import annotations

from aiogram import Router

router = Router()
