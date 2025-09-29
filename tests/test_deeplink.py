from __future__ import annotations

from app.services.deep_links import decode_payload, encode_payload


def test_deep_link_roundtrip():
    sku = "BUTTERFLY-14"
    payload = encode_payload(sku)
    assert decode_payload(payload) == sku


def test_deep_link_invalid():
    assert decode_payload("invalid") is None
