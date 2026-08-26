from decimal import Decimal
import hashlib
import hmac

import pytest

from paper_live import (
    EnvironmentController,
    EnvironmentTransitionError,
    ExecutionEnvironmentMode,
    ExecutionGateway,
    OrderRequest,
    OrderSide,
    PaperAccount,
    VirtualMatchingEngine,
)
from paper_live.live_approval import LiveApprovalGate

SECRET = "test-secret"
TOKEN = hmac.new(SECRET.encode(), b"environment-transition", hashlib.sha256).hexdigest()


def controller():
    return EnvironmentController(transition_secret=SECRET)


def test_default_is_paper_and_live_skill_is_denied():
    c = controller()
    assert c.get_current_mode() is ExecutionEnvironmentMode.PAPER_SANDBOX
    assert c.is_skill_allowed("skill-virtual-matching-engine")
    assert not c.is_skill_allowed("skill-toss-broker")
    with pytest.raises(EnvironmentTransitionError):
        c.assert_skill_allowed("skill-toss-broker")


def test_invalid_transition_token_is_rejected():
    c = controller()
    with pytest.raises(EnvironmentTransitionError):
        c.set_mode(ExecutionEnvironmentMode.REAL_LIVE, "bad-token")


def test_authorized_mode_change_is_auditable():
    c = controller()
    assert c.set_mode(ExecutionEnvironmentMode.VIRTUAL_BACKTEST, TOKEN, actor="test")
    snapshot = c.snapshot()
    assert snapshot.mode is ExecutionEnvironmentMode.VIRTUAL_BACKTEST
    assert snapshot.version == 1
    assert snapshot.changed_by == "test"


def test_paper_buy_and_sell_ledger():
    account = PaperAccount(cash=Decimal("100000"))
    engine = VirtualMatchingEngine(account)
    buy = engine.execute(
        OrderRequest("005930", OrderSide.BUY, Decimal("10"), client_order_id="b1"),
        Decimal("7000"),
    )
    assert buy.quantity == Decimal("10")
    assert account.positions["005930"] == Decimal("10")
    engine.execute(OrderRequest("005930", OrderSide.SELL, Decimal("10"), client_order_id="s1"), Decimal("7100"))
    assert account.positions["005930"] == Decimal("0")


def test_gateway_refuses_live_execution():
    gate = LiveApprovalGate()
    gate.approve("test-operator", "gateway isolation test")
    c = EnvironmentController(transition_secret=SECRET, live_approval_gate=gate)
    c.set_mode(ExecutionEnvironmentMode.REAL_LIVE, TOKEN)
    gateway = ExecutionGateway(c, VirtualMatchingEngine(PaperAccount(Decimal("100000"))))
    with pytest.raises(EnvironmentTransitionError):
        gateway.execute(OrderRequest("005930", OrderSide.BUY, Decimal("1"), client_order_id="live-test"), Decimal("7000"))
