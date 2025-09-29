"""Client wrapper for amoCRM API v4."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import aiohttp

LOGGER = logging.getLogger(__name__)


class AmoAuthError(RuntimeError):
    pass


@dataclass(slots=True)
class AmoCredentials:
    domain: str
    client_id: str
    client_secret: str
    redirect_uri: str
    refresh_token: str
    access_token: Optional[str] = None
    token_expires_at: float = 0.0

    def api_base(self) -> str:
        return f"https://{self.domain}/api/v4"


class AmoCRMClient:
    def __init__(self, credentials: AmoCredentials) -> None:
        self._cred = credentials
        self._lock = asyncio.Lock()

    async def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        await self.ensure_access_token()
        headers = kwargs.setdefault("headers", {})
        headers["Authorization"] = f"Bearer {self._cred.access_token}"
        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, **kwargs) as response:
                if response.status == 401:
                    LOGGER.info("Access token expired, refreshing")
                    await self.refresh_token()
                    headers["Authorization"] = f"Bearer {self._cred.access_token}"
                    async with session.request(method, url, **kwargs) as retry:
                        retry.raise_for_status()
                        return await retry.json()
                response.raise_for_status()
                if response.content_type == "application/json":
                    return await response.json()
                return await response.text()

    async def ensure_access_token(self) -> None:
        async with self._lock:
            if self._cred.access_token and time.time() < self._cred.token_expires_at - 60:
                return
            await self.refresh_token()

    async def refresh_token(self) -> None:
        LOGGER.debug("Refreshing amoCRM access token")
        async with aiohttp.ClientSession() as session:
            payload = {
                "client_id": self._cred.client_id,
                "client_secret": self._cred.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": self._cred.refresh_token,
                "redirect_uri": self._cred.redirect_uri,
            }
            async with session.post(
                f"https://{self._cred.domain}/oauth2/access_token", json=payload
            ) as response:
                if response.status >= 400:
                    text = await response.text()
                    raise AmoAuthError(f"Unable to refresh token: {response.status} {text}")
                data = await response.json()
        self._cred.access_token = data["access_token"]
        self._cred.refresh_token = data.get("refresh_token", self._cred.refresh_token)
        self._cred.token_expires_at = time.time() + int(data.get("expires_in", 3600))
        if api_domain := data.get("api_domain"):
            self._cred.domain = api_domain.replace("https://", "").rstrip("/")

    async def create_lead_with_contact(
        self,
        contact_name: str,
        phone: str,
        lead_name: str,
        price: float,
        pipeline_id: int,
        status_id: int,
        note: str,
        tags: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        payload = [
            {
                "name": lead_name,
                "price": price,
                "pipeline_id": pipeline_id,
                "status_id": status_id,
                "_embedded": {
                    "contacts": [
                        {
                            "name": contact_name,
                            "custom_fields_values": [
                                {
                                    "field_code": "PHONE",
                                    "values": [{"value": phone}],
                                }
                            ],
                        }
                    ]
                },
            }
        ]
        if tags:
            payload[0]["_embedded"]["tags"] = [{"name": tag} for tag in tags]
        response = await self._request(
            "POST",
            f"{self._cred.api_base()}/leads/complex",
            json=payload,
        )
        lead = response["_embedded"]["leads"][0]
        lead_id = lead["id"]
        await self._request(
            "POST",
            f"{self._cred.api_base()}/leads/{lead_id}/notes",
            json=[{"note_type": "common", "params": {"text": note}}],
        )
        return lead
