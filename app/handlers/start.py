"""Start and help command handlers."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.filters.command import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.services.deep_links import decode_payload
from app.texts import HELP_TEXT, WELCOME_TEXT

router = Router()


@router.message(CommandStart())
async def cmd_start(
    message: Message, command: CommandObject | None = None, state: FSMContext | None = None
) -> None:
    payload = None
    if command and command.args:
        payload = decode_payload(command.args)
        if payload:
            if state:
                await state.update_data(sku=payload)
    await message.answer(WELCOME_TEXT)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)
