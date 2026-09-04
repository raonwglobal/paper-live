from decimal import Decimal
import pytest
from paper_live.environment import EnvironmentController
from paper_live.execution import ExecutionGateway, PaperOrderRequest, OrderSide, PaperAccount, VirtualMatchingEngine
from paper_live.order_lifecycle import OrderStatus

def test_gateway_repeated_filled_order_does_not_double_spend():
    gateway = ExecutionGateway(EnvironmentController(), VirtualMatchingEngine(PaperAccount(Decimal("10000")), slippage_bps=Decimal("0")))
    order = PaperOrderRequest("ABC", OrderSide.BUY, Decimal("10"), client_order_id="idem-1")
    first = gateway.execute(order, Decimal("100"))
    cash_after = gateway.paper.account.cash
    second = gateway.execute(order, Decimal("100"))
    assert first.quantity == Decimal("10")
    assert second.quantity == Decimal("10")
    assert gateway.paper.account.cash == cash_after
    assert gateway.lifecycle.get("idem-1").status is OrderStatus.FILLED

def test_gateway_partial_fill_only_executes_remaining_quantity():
    lifecycle_engine = VirtualMatchingEngine(PaperAccount(Decimal("10000")), slippage_bps=Decimal("0"), max_fill_ratio=Decimal("0.5"))
    gateway = ExecutionGateway(EnvironmentController(), lifecycle_engine)
    order = PaperOrderRequest("ABC", OrderSide.BUY, Decimal("10"), client_order_id="partial-1")
    first = gateway.execute(order, Decimal("100"))
    second = gateway.execute(order, Decimal("100"))
    assert first.quantity == Decimal("5")
    assert second.quantity == Decimal("2.5")
    assert gateway.lifecycle.get("partial-1").filled_quantity == Decimal("7.5")

def test_gateway_requires_client_order_id():
    gateway = ExecutionGateway(EnvironmentController(), VirtualMatchingEngine(PaperAccount(Decimal("1000"))))
    with pytest.raises(ValueError):
        gateway.execute(PaperOrderRequest("ABC", OrderSide.BUY, Decimal("1")), Decimal("100"))
