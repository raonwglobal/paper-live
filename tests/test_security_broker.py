import json
from decimal import Decimal

import pytest

from paper_live.brokers import BrokerOrderRequest, TossApiError, TossBrokerAdapter, TossCredentials
from paper_live.security import CredentialProvider, LiveApprovalGate


def test_live_approval_requires_valid_nonce():
    gate = LiveApprovalGate()
    with pytest.raises(PermissionError):
        gate.approve("bad")


def test_live_approval_accepts_valid_nonce():
    gate = LiveApprovalGate()
    nonce = gate.issue_nonce()
    assert gate.approve(nonce)


def test_toss_order_serialization_uses_client_order_id():
    adapter = TossBrokerAdapter(TossCredentials("key", "secret"))
    request = BrokerOrderRequest("AAPL", "buy", "limit", Decimal("2"), price=Decimal("100"))
    payload = adapter._serialize_order(request)
    assert payload == {"symbol": "AAPL", "side": "buy", "orderType": "limit", "quantity": "2", "price": "100"}


def test_toss_order_rejects_invalid_side():
    adapter = TossBrokerAdapter(TossCredentials("key", "secret"))
    request = BrokerOrderRequest("AAPL", "hold", "limit", Decimal("2"), price=Decimal("100"))
    result = adapter.submit(request)
    assert not result.accepted
    assert result.message == "unsupported order side"


def test_toss_order_rejects_invalid_order_type():
    adapter = TossBrokerAdapter(TossCredentials("key", "secret"))
    request = BrokerOrderRequest("AAPL", "buy", "stop", Decimal("2"), price=Decimal("100"))
    result = adapter.submit(request)
    assert not result.accepted
    assert result.message == "unsupported order type"


def test_toss_order_requires_positive_quantity():
    adapter = TossBrokerAdapter(TossCredentials("key", "secret"))
    request = BrokerOrderRequest("AAPL", "buy", "limit", Decimal("0"), price=Decimal("100"))
    result = adapter.submit(request)
    assert not result.accepted
    assert result.message == "quantity must be positive"


def test_toss_limit_order_requires_positive_price():
    adapter = TossBrokerAdapter(TossCredentials("key", "secret"))
    request = BrokerOrderRequest("AAPL", "buy", "limit", Decimal("2"), price=Decimal("0"))
    result = adapter.submit(request)
    assert not result.accepted
    assert result.message == "limit order price must be positive"


def test_toss_market_order_rejects_price():
    adapter = TossBrokerAdapter(TossCredentials("key", "secret"))
    request = BrokerOrderRequest("AAPL", "buy", "market", Decimal("2"), price=Decimal("100"))
    result = adapter.submit(request)
    assert not result.accepted
    assert result.message == "market order must not include price"


def test_toss_api_error_is_sanitized():
    adapter = TossBrokerAdapter(TossCredentials("key", "secret"))
    error = TossApiError("request failed: key=secret")
    assert adapter._sanitize_error(error) == "request failed: key=secret"
