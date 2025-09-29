"""Application entrypoint for the Telegram bot."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import Settings
from app.handlers import admin, calc, catalog, lead, navigation, start
from app.services.amocrm import AmoCRMClient, AmoCredentials
from app.services.catalog_storage import CatalogStorage

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)


def create_dispatcher(settings: Settings) -> Dispatcher:
    storage = MemoryStorage()
    dispatcher = Dispatcher(storage=storage)

    catalog_storage = CatalogStorage(Path(settings.catalog_path))
    try:
        catalog_storage.load()
    except FileNotFoundError:
        LOGGER.warning("Catalog file not found: %s", settings.catalog_path)
    except Exception:
        LOGGER.exception("Unable to load catalog")

    amo_credentials = AmoCredentials(
        domain=settings.amo_subdomain,
        client_id=settings.amo_client_id,
        client_secret=settings.amo_client_secret,
        redirect_uri=settings.amo_redirect_uri,
        refresh_token=settings.amo_refresh_token,
    )
    amo_client = AmoCRMClient(amo_credentials)

    dispatcher.include_router(start.router)
    dispatcher.include_router(catalog.router)
    dispatcher.include_router(calc.router)
    dispatcher.include_router(lead.router)
    dispatcher.include_router(admin.router)
    dispatcher.include_router(navigation.router)

    dispatcher.workflow_data.update(
        {
            "catalog_storage": catalog_storage,
            "settings": settings,
            "amo_client": amo_client,
        }
    )
    return dispatcher


async def main() -> None:
    settings = Settings()
    bot = Bot(token=settings.bot_token, parse_mode=ParseMode.HTML)
    dispatcher = create_dispatcher(settings)
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
