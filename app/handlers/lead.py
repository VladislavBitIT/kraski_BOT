"""Handlers for the lead capture flow."""
from __future__ import annotations

from typing import Dict

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.models.state import LeadStates
from app.services.amocrm import AmoCRMClient
from app.texts import LEAD_ERROR, LEAD_SUCCESS, PHONE_ERROR
from app.utils.validation import validate_phone

router = Router()


def _get_amo_client(data: Dict[str, object]) -> AmoCRMClient:
    return data["amo_client"]  # type: ignore[return-value]


def _get_settings(data: Dict[str, object]):
    return data["settings"]


@router.callback_query(F.data == "lead:start")
async def lead_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(LeadStates.full_name)
    await callback.message.answer("Введите ваше ФИО")


@router.message(LeadStates.full_name)
async def lead_full_name(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if len(text) < 2:
        await message.answer("Имя слишком короткое. Попробуйте ещё раз.")
        return
    await state.update_data(lead_full_name=text)
    await state.set_state(LeadStates.phone)
    await message.answer("Введите номер телефона")


@router.message(LeadStates.phone)
async def lead_phone(message: Message, state: FSMContext, data: Dict[str, object]) -> None:
    phone = message.text.strip()
    if not validate_phone(phone):
        await message.answer(PHONE_ERROR)
        return
    await state.update_data(lead_phone=phone)
    amo = _get_amo_client(data)
    settings = _get_settings(data)
    user_data = await state.get_data()
    note = user_data.get("calc_result", "")
    sku = user_data.get("sku", "")
    paint_name = user_data.get("paint_name", sku)
    lead_name = f"{sku} · {paint_name}" if sku else paint_name or "Заявка из бота"
    price = user_data.get("calc_price", 0)
    try:
        await amo.create_lead_with_contact(
            contact_name=user_data.get("lead_full_name", "Клиент"),
            phone=phone,
            lead_name=lead_name,
            price=price,
            pipeline_id=getattr(settings, "amo_pipeline_id"),
            status_id=getattr(settings, "amo_status_id"),
            note=note,
            tags=["TelegramBot", "РасчётКраски"],
        )
    except Exception:
        await message.answer(LEAD_ERROR)
    else:
        await message.answer(LEAD_SUCCESS.format(phone=phone))
    finally:
        await state.set_state(LeadStates.done)
