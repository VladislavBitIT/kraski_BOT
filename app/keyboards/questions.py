"""Keyboards for the questionnaire flow."""
from __future__ import annotations

from aiogram.utils.keyboard import InlineKeyboardBuilder


def color_keyboard() -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(text="Ещё не выбран", callback_data="color:none")
    builder.button(text="Ввести номер", callback_data="color:manual")
    builder.adjust(1)
    return builder


def tool_keyboard() -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(text="Валик", callback_data="tool:roller")
    builder.button(text="Краскопульт", callback_data="tool:sprayer")
    builder.adjust(1)
    return builder


def reserve_keyboard() -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    for pct in (0, 5, 10, 15):
        builder.button(text=f"{pct}%", callback_data=f"reserve:{pct}")
    builder.adjust(2)
    return builder


def surface_keyboard() -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(text="Стена", callback_data="surface:wall")
    builder.button(text="Потолок", callback_data="surface:ceiling")
    builder.adjust(1)
    return builder


def primer_keyboard() -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(text="Считать только краску", callback_data="primer:none")
    builder.button(text="Добавить грунт", callback_data="primer:ground")
    builder.button(text="Добавить праймер", callback_data="primer:qbase")
    builder.button(text="Добавить оба", callback_data="primer:both")
    builder.adjust(1)
    return builder
