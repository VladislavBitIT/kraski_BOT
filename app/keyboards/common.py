"""Common inline keyboards used across handlers."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def back_keyboard(callback: str) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Назад", callback_data=callback)
    builder.adjust(1)
    return builder


def single_button(text: str, callback: str) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(text=text, callback_data=callback)
    builder.adjust(1)
    return builder
