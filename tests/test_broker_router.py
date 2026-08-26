import pytest
from decimal import Decimal
from paper_live.brokers.protocol import OrderRequest, OrderResult, LiveBrokerDenied
from paper_live.brokers.safe_router import BrokerRouter

class FakeBroker:
    name = "fake"
    def submit(self, request): return OrderResult("fake", "1", True)
    def cancel(self, order_id): return True

def test_live_only():
    router = BrokerRouter({"fake": FakeBroker()})
    with pytest.raises(LiveBrokerDenied): router.submit("PAPER_SANDBOX", "fake", OrderRequest("AAA", "buy", Decimal("1")))
    assert router.submit("REAL_LIVE", "fake", OrderRequest("AAA", "buy", Decimal("1"))).accepted
