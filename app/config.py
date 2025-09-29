"""Application configuration objects."""
from __future__ import annotations

from pathlib import Path
from typing import List

from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    bot_token: str = Field(..., env="BOT_TOKEN")
    admin_ids: List[int] = Field(default_factory=list, env="ADMIN_IDS")

    amo_subdomain: str = Field(..., env="AMO_SUBDOMAIN")
    amo_client_id: str = Field(..., env="AMO_CLIENT_ID")
    amo_client_secret: str = Field(..., env="AMO_CLIENT_SECRET")
    amo_redirect_uri: str = Field(..., env="AMO_REDIRECT_URI")
    amo_refresh_token: str = Field(..., env="AMO_REFRESH_TOKEN")
    amo_pipeline_id: int = Field(..., env="AMO_PIPELINE_ID")
    amo_status_id: int = Field(..., env="AMO_STATUS_ID")

    catalog_path: Path = Field(Path("./app/data/catalog.xlsx"), env="CATALOG_PATH")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    @staticmethod
    def _parse_list(value: str) -> List[int]:
        return [int(v.strip()) for v in value.split(",") if v.strip()]

    @classmethod
    def parse_admin_ids(cls, value: str | List[int]) -> List[int]:
        if isinstance(value, list):
            return value
        return cls._parse_list(value)

    @classmethod
    def customise_sources(cls, init_settings, env_settings, file_secret_settings):
        return (
            init_settings,
            env_settings,
            file_secret_settings,
        )

    def __init__(self, **values):
        if "admin_ids" in values and isinstance(values["admin_ids"], str):
            values["admin_ids"] = self._parse_list(values["admin_ids"])
        super().__init__(**values)
