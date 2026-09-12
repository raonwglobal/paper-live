import json
from decimal import Decimal

import pytest

from paper_live.brokers import BrokerOrderRequest, KbApiError, KbBrokerAdapter, KbCredentials


def test_kb_submit_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("PAPER_LIVE_ENABLE_LIVE", raising=False)
    adapter = KbBrokerAdapter(KbCredentials("key", "secret"))
    with pytest.raises(PermissionError):
        adapter.submit(BrokerOrderRequest("005930", "BUY", Decimal("1"), "limit", Decimal("70000")))


def test_kb_buy_limit_serializes_ssam1802_body(monkeypatch):
    monkeypatch.setenv("PAPER_LIVE_ENABLE_LIVE", "true")
    adapter = KbBrokerAdapter(KbCredentials("key", "secret"))
    calls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"ordr_no":"K-100","o_msg":"ok","o_clsf":"0"}'

    def fake_urlopen(request, timeout):
        calls.append(request)
        if request.full_url.endswith("/oauth2/token"):
            response = Response()
            response.read = lambda: b'{"access_token":"token"}'
            return response
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    result = adapter.submit(BrokerOrderRequest("005930", "buy", Decimal("2"), "limit", Decimal("70000")))
    assert result.accepted is True
    assert result.order_id == "K-100"
    body = json.loads(calls[-1].data.decode())
    assert calls[-1].full_url.endswith("/api/v1/ssam1802")
    assert body == {
        "mkt_tm_clsf": "1",
        "is_cd": "005930",
        "ordr_q": "2",
        "ordr_uprc": "70000",
        "ordr_ccd": "00",
    }


def test_kb_sell_uses_ssam1801(monkeypatch):
    monkeypatch.setenv("PAPER_LIVE_ENABLE_LIVE", "true")
    adapter = KbBrokerAdapter(KbCredentials("key", "secret"))
    calls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"ordr_no":"K-200","o_msg":"ok"}'

    def fake_urlopen(request, timeout):
        calls.append(request)
        if request.full_url.endswith("/oauth2/token"):
            response = Response()
            response.read = lambda: b'{"access_token":"token"}'
            return response
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    result = adapter.submit(BrokerOrderRequest("005930", "SELL", Decimal("1"), "market"))
    assert result.accepted is True
    assert calls[-1].full_url.endswith("/api/v1/ssam1801")
    body = json.loads(calls[-1].data.decode())
    assert body["ordr_ccd"] == "03"
    assert body["ordr_uprc"] == "0"


def test_kb_market_order_rejects_price_before_network(monkeypatch):
    monkeypatch.setenv("PAPER_LIVE_ENABLE_LIVE", "true")
    adapter = KbBrokerAdapter(KbCredentials("key", "secret"))
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: pytest.fail("network call not expected"))
    with pytest.raises(ValueError, match="market orders must not include price"):
        adapter.submit(BrokerOrderRequest("005930", "BUY", Decimal("1"), "market", Decimal("70000")))


def test_kb_fractional_quantity_rejected(monkeypatch):
    monkeypatch.setenv("PAPER_LIVE_ENABLE_LIVE", "true")
    adapter = KbBrokerAdapter(KbCredentials("key", "secret"))
    with pytest.raises(ValueError, match="whole-share"):
        adapter.submit(BrokerOrderRequest("005930", "BUY", Decimal("1.5"), "limit", Decimal("1000")))


def test_kb_missing_ordr_no_is_not_accepted(monkeypatch):
    monkeypatch.setenv("PAPER_LIVE_ENABLE_LIVE", "true")
    adapter = KbBrokerAdapter(KbCredentials("key", "secret"))

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(self.payload).encode()

    def fake_urlopen(request, timeout):
        if request.full_url.endswith("/oauth2/token"):
            return Response({"access_token": "token"})
        return Response({"o_msg": "fail", "o_clsf": "9"})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    result = adapter.submit(BrokerOrderRequest("005930", "BUY", Decimal("1"), "market"))
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


def test_kb_cancel_requires_symbol_and_posts_ssam1806(monkeypatch):
    monkeypatch.setenv("PAPER_LIVE_ENABLE_LIVE", "true")
    adapter = KbBrokerAdapter(KbCredentials("key", "secret"))
    calls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"ordr_no":"C-1","o_msg":"ok"}'

    def fake_urlopen(request, timeout):
        calls.append(request)
        if request.full_url.endswith("/oauth2/token"):
            response = Response()
            response.read = lambda: b'{"access_token":"token"}'
            return response
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    with pytest.raises(ValueError, match="symbol is required"):
        adapter.cancel("ord-1")
    assert adapter.cancel("ord-1", symbol="005930") is True
    assert calls[-1].full_url.endswith("/api/v1/ssam1806")
    body = json.loads(calls[-1].data.decode())
    assert body == {"is_cd": "005930", "crct_clsf": "2", "orgn_ordr_no": "ord-1"}
