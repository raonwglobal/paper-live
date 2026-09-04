from decimal import Decimal
import hashlib
import hmac
import pytest
from paper_live.environment import EnvironmentController, EnvironmentTransitionError, ExecutionEnvironmentMode
from paper_live.execution import ExecutionGateway, PaperOrderRequest, OrderSide, PaperAccount, VirtualMatchingEngine
from paper_live.live_approval import LiveApprovalGate
from paper_live.risk import RiskGuardian, RiskLimits

def _token(secret: str) -> str:
    return hmac.new(secret.encode(), b"environment-transition", hashlib.sha256).hexdigest()

def test_paper_gateway_fail_closed_in_live_mode_even_after_approval():
    secret = "secret"
    gate = LiveApprovalGate()
    gate.approve("operator", "test")
    controller = EnvironmentController(transition_secret=secret, live_approval_gate=gate)
    controller.set_mode(ExecutionEnvironmentMode.REAL_LIVE, _token(secret))
    gateway = ExecutionGateway(controller, VirtualMatchingEngine(PaperAccount(Decimal("10000"))))
    with pytest.raises(EnvironmentTransitionError):
        gateway.execute(PaperOrderRequest("ABC", OrderSide.BUY, Decimal("1"), client_order_id="live-block"), Decimal("100"))

def test_risk_circuit_breaker_blocks_order():
    controller = EnvironmentController()
    account = PaperAccount(Decimal("10000"))
    risk = RiskGuardian(controller, account, RiskLimits(max_order_notional=Decimal("50")))
    order = PaperOrderRequest("ABC", OrderSide.BUY, Decimal("1"), client_order_id="risk-1")
    with pytest.raises(PermissionError):
        risk.approve(order, Decimal("100"))
    risk.circuit_breaker.trip()
    with pytest.raises(PermissionError):
        risk.approve(PaperOrderRequest("ABC", OrderSide.BUY, Decimal("1"), client_order_id="risk-2"), Decimal("1"))

def test_paper_engine_rejects_insufficient_cash():
    engine = VirtualMatchingEngine(PaperAccount(Decimal("10")), slippage_bps=Decimal("0"))
    with pytest.raises(ValueError):
        engine.execute(PaperOrderRequest("ABC", OrderSide.BUY, Decimal("1"), client_order_id="cash-1"), Decimal("100"))
