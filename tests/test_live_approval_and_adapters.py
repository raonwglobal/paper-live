import pytest
from decimal import Decimal
from paper_live.brokers.protocol import BrokerOrderRequest, OrderResult, LiveBrokerDenied
from paper_live.brokers.safe_router import BrokerRouter
from paper_live.security.live_approval_gate import LiveApprovalGate

class FakeBroker:
    name = "fake"
    def submit(self, request): return OrderResult("fake", "1", True)
    def cancel(self, order_id): return True


def test_live_requires_explicit_approval():
    gate = LiveApprovalGate()
    router = BrokerRouter({"fake": FakeBroker()}, gate)
    req = BrokerOrderRequest("005930", "BUY", Decimal("1"))
    with pytest.raises(LiveBrokerDenied):
        router.submit("REAL_LIVE", "fake", req)
    approval = gate.approve("operator")
    assert router.submit("REAL_LIVE", "fake", req, approval.approval_id).accepted


def test_paper_never_reaches_broker():
    gate = LiveApprovalGate()
    router = BrokerRouter({"fake": FakeBroker()}, gate)
    with pytest.raises(LiveBrokerDenied):
        router.submit("PAPER_SANDBOX", "fake", BrokerOrderRequest("005930", "BUY", Decimal("1")), None)
