"""Administrative handlers."""
from __future__ import annotations

from pathlib import Path
from typing import Dict

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.models.state import AdminStates
from app.services.catalog_storage import CatalogStorage
from app.services.excel_loader import CatalogValidationError
from app.texts import EXCEL_ERROR, EXCEL_SUCCESS

router = Router()


def _is_admin(user_id: int, data: Dict[str, object]) -> bool:
    settings = data.get("settings")
    if not settings:
        return False
    return int(user_id) in getattr(settings, "admin_ids", [])


@router.message(Command("admin_excel"))
async def admin_excel(message: Message, state: FSMContext, data: Dict[str, object]) -> None:
    if not _is_admin(message.from_user.id, data):  # type: ignore[arg-type]
        await message.answer("Недостаточно прав для выполнения команды.")
        return
    await state.set_state(AdminStates.waiting_excel)
    await message.answer("Отправьте Excel-файл (xlsx) с каталогом.")


@router.message(AdminStates.waiting_excel)
async def admin_excel_upload(
    message: Message, state: FSMContext, data: Dict[str, object]
) -> None:
    if not message.document:
        await message.answer("Нужно отправить файл в формате .xlsx")
        return
    storage: CatalogStorage = data["catalog_storage"]  # type: ignore[assignment]
    file = await message.bot.get_file(message.document.file_id)
    destination = storage.path
    temp_path = Path(destination).with_suffix(".upload.xlsx")
    await message.bot.download_file(file.file_path, destination=temp_path)
    try:
        storage.path = temp_path
        _, report = storage.load()
        temp_path.replace(destination)
        await message.answer(
            EXCEL_SUCCESS.format(
                paints=report.paints,
                primers=report.primers,
                skipped=", ".join(report.skipped) or "0",
            )
        )
    except CatalogValidationError as exc:
        await message.answer(EXCEL_ERROR.format(message=str(exc)))
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        storage.path = destination
        await state.clear()
