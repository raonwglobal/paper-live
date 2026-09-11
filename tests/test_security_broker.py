import json
from decimal import Decimal

import pytest

from paper_live.brokers import BrokerOrderRequest, TossApiError, TossBrokerAdapter, TossCredentials
from paper_live.security import CredentialProvider, LiveApprovalGate


def test_live_approval_requires_valid_nonce():
    gate = LiveApprovalGate()
    with pytest.raises(PermissionError):
        gate.approve("operator", "bad")
    gate.approve("operator", gate.nonce)
    assert gate.approved()


def test_toss_requires_credentials(monkeypatch):
    monkeypatch.delenv("TOSS_API_TOKEN", raising=False)
    monkeypatch.delenv("TOSS_ACCOUNT_SEQ", raising=False)
    with pytest.raises(Exception):
        CredentialProvider().load_toss()


def test_toss_submit_is_disabled_by_default(monkeypatch):
    monkeypatch.setenv("TOSS_API_TOKEN", "dummy")
    monkeypatch.setenv("TOSS_ACCOUNT_SEQ", "1")
    monkeypatch.delenv("PAPER_LIVE_ENABLE_LIVE", raising=False)
    adapter = TossBrokerAdapter()
    with pytest.raises(PermissionError):
        adapter.submit("005930", "BUY", Decimal("1"), Decimal("70000"))


def test_toss_dto_limit_order_serializes_price(monkeypatch):
    monkeypatch.setenv("PAPER_LIVE_ENABLE_LIVE", "true")
    adapter = TossBrokerAdapter(TossCredentials("client", "secret", "1"))
    calls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"result":{"orderId":"T-123"}}'

        def __iter__(self):
            return iter(())

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
    assert result.order_id == "T-123"
    body = json.loads(calls[-1].data.decode())
    assert body == {
        "symbol": "005930",
        "side": "BUY",
        "orderType": "LIMIT",
        "quantity": "2",
        "price": "70000",
    }


def test_toss_market_order_rejects_price_before_network(monkeypatch):
    monkeypatch.setenv("PAPER_LIVE_ENABLE_LIVE", "true")
    adapter = TossBrokerAdapter(TossCredentials("client", "secret", "1"))
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: pytest.fail("network call not expected"))

    with pytest.raises(ValueError, match="market orders must not include price"):
        adapter.submit(BrokerOrderRequest("005930", "BUY", Decimal("1"), "market", Decimal("70000")))


def test_toss_missing_order_id_is_not_accepted(monkeypatch):
    monkeypatch.setenv("PAPER_LIVE_ENABLE_LIVE", "true")
    adapter = TossBrokerAdapter(TossCredentials("client", "secret", "1"))

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
        return Response({"result": {}})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    result = adapter.submit(BrokerOrderRequest("005930", "BUY", Decimal("1"), "market"))
    assert result.accepted is False
    assert result.order_id == ""


def test_toss_api_error_does_not_expose_exception_text(monkeypatch):
    monkeypatch.setenv("PAPER_LIVE_ENABLE_LIVE", "true")
    adapter = TossBrokerAdapter(TossCredentials("client", "SECRET-VALUE", "1"))

    def fake_urlopen(*args, **kwargs):
        raise RuntimeError("SECRET-VALUE leaked")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    with pytest.raises(TossApiError) as exc_info:
        adapter._token_value()
    assert "SECRET-VALUE" not in str(exc_info.value)
    assert "RuntimeError" in str(exc_info.value)
