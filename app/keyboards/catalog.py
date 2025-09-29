"""Keyboards for catalog navigation."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def categories_keyboard(categories: list[str], prefix: str = "cat") -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    for category in categories:
        builder.button(text=category, callback_data=f"{prefix}:{category}")
    builder.adjust(1)
    return builder


def paint_actions_keyboard(sku: str, url: str | None) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(text="Рассчитать", callback_data=f"paint:{sku}")
    builder.button(text="Скопировать ссылку", callback_data=f"share:{sku}")
    if url:
        builder.button(text="Открыть на сайте", url=url)
    builder.adjust(1)
    return builder
