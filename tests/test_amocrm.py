from __future__ import annotations

import asyncio
import json
import time

from app.services.amocrm import AmoCRMClient, AmoCredentials


class FakeResponse:
    def __init__(self, status: int, payload: dict):
        self.status = status
        self._payload = payload
        self.content_type = "application/json"

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self._payload

    async def text(self):
        return json.dumps(self._payload)

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")


class FakeSession:
    def __init__(self, responses):
        self.responses = responses
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def request(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        return self.responses.pop(0)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)


def test_create_lead_with_contact(monkeypatch):
    responses = [
        FakeResponse(200, {"_embedded": {"leads": [{"id": 1}]}}),
        FakeResponse(200, {"result": "ok"}),
    ]
    session = FakeSession(responses)

    def fake_client_session(*args, **kwargs):
        return session

    monkeypatch.setattr("app.services.amocrm.aiohttp.ClientSession", fake_client_session)

    credentials = AmoCredentials(
        domain="example.amocrm.ru",
        client_id="id",
        client_secret="secret",
        redirect_uri="https://example.com",
        refresh_token="refresh",
        access_token="token",
        token_expires_at=time.time() + 3600,
    )
    client = AmoCRMClient(credentials)

    async def run():
        lead = await client.create_lead_with_contact(
            contact_name="Иван Иванов",
            phone="+79001234567",
            lead_name="BUTTERFLY",
            price=1000,
            pipeline_id=1,
            status_id=2,
            note="Примечание",
            tags=["TelegramBot"],
        )
        return lead

    lead = asyncio.run(run())
    assert lead["id"] == 1
    assert len(session.requests) == 2
