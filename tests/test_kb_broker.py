import json
from decimal import Decimal

import pytest

from paper_live.brokers import (
    BrokerOrderRequest,
    KbApiError,
    KbBrokerAdapter,
    KbCredentials,
    KbOrderSchemaUnavailable,
)


def test_kb_submit_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("PAPER_LIVE_ENABLE_LIVE", raising=False)
    adapter = KbBrokerAdapter(KbCredentials("key", "secret"))
    with pytest.raises(PermissionError):
        adapter.submit(BrokerOrderRequest("005930", "BUY", Decimal("1"), "limit", Decimal("70000")))


def test_kb_submit_fails_closed_before_network(monkeypatch):
    monkeypatch.setenv("PAPER_LIVE_ENABLE_LIVE", "true")
    adapter = KbBrokerAdapter(KbCredentials("key", "secret"))
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: pytest.fail("network call not expected"))
    with pytest.raises(KbOrderSchemaUnavailable, match="not fully pinned"):
        adapter.submit(BrokerOrderRequest("005930", "BUY", Decimal("1"), "limit", Decimal("70000")))


def test_kb_sell_path_is_pinned_without_guessing_payload():
    assert KbBrokerAdapter._path_for_side("BUY") == "/api/v1/ssam1802"
    assert KbBrokerAdapter._path_for_side("SELL") == "/api/v1/ssam1801"


def test_kb_market_order_rejects_price_before_schema_check(monkeypatch):
    monkeypatch.setenv("PAPER_LIVE_ENABLE_LIVE", "true")
    adapter = KbBrokerAdapter(KbCredentials("key", "secret"))
    with pytest.raises(ValueError, match="market orders must not include price"):
        adapter.submit(BrokerOrderRequest("005930", "BUY", Decimal("1"), "market", Decimal("70000")))


def test_kb_fractional_quantity_rejected(monkeypatch):
    monkeypatch.setenv("PAPER_LIVE_ENABLE_LIVE", "true")
    adapter = KbBrokerAdapter(KbCredentials("key", "secret"))
    with pytest.raises(KbOrderSchemaUnavailable):
        adapter.submit(BrokerOrderRequest("005930", "BUY", Decimal("1.5"), "limit", Decimal("1000")))


def test_kb_missing_ordr_no_is_not_accepted():
    result = KbBrokerAdapter._result_from_response({"o_msg": "fail", "o_clsf": "9"})
    assert result.accepted is False
    assert result.order_id == ""


def test_kb_api_error_does_not_expose_exception_text(monkeypatch):
    monkeypatch.setenv("PAPER_LIVE_ENABLE_LIVE", "true")
    adapter = KbBrokerAdapter(KbCredentials("key", "SECRET-VALUE"))

    def fake_urlopen(*args, **kwargs):
        raise RuntimeError("SECRET-VALUE leaked")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    with pytest.raises(KbApiError) as exc_info:
        adapter._token_value()
    assert "SECRET-VALUE" not in str(exc_info.value)
    assert "RuntimeError" in str(exc_info.value)


def test_kb_cancel_requires_symbol_and_fails_closed(monkeypatch):
    monkeypatch.setenv("PAPER_LIVE_ENABLE_LIVE", "true")
    adapter = KbBrokerAdapter(KbCredentials("key", "secret"))
    with pytest.raises(ValueError, match="symbol is required"):
        adapter.cancel("ord-1")
    with pytest.raises(KbOrderSchemaUnavailable, match="not fully pinned"):
        adapter.cancel("ord-1", symbol="005930")
