import pytest
from decimal import Decimal
from paper_live.brokers.protocol import OrderRequest, OrderResult, LiveBrokerDenied
from paper_live.brokers.safe_router import BrokerRouter
from paper_live.security.live_approval_gate import LiveApprovalGate

class FakeBroker:
    name = "fake"
    def submit(self, request): return OrderResult("fake", "1", True)
    def cancel(self, order_id): return True


def test_live_only():
    gate = LiveApprovalGate()
    router = BrokerRouter({"fake": FakeBroker()}, approval_gate=gate)
    request = OrderRequest("AAA", "buy", Decimal("1"))
    with pytest.raises(LiveBrokerDenied):
        router.submit("PAPER_SANDBOX", "fake", request)
    with pytest.raises(LiveBrokerDenied):
        router.submit("REAL_LIVE", "fake", request)
    approval = gate.approve("test-suite")
    result = router.submit("REAL_LIVE", "fake", request, approval.approval_id)
    assert result.accepted
