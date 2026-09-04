from decimal import Decimal
from paper_live.execution import ExecutionGateway, PaperOrderRequest, OrderSide, PaperAccount, VirtualMatchingEngine
from paper_live.environment import EnvironmentController
from paper_live.pnl import PortfolioLedger, Side


def test_paper_fill_can_be_applied_to_portfolio_pnl():
    controller = EnvironmentController()
    account = PaperAccount(cash=Decimal("10000"))
    engine = VirtualMatchingEngine(account, slippage_bps=Decimal("0"))
    gateway = ExecutionGateway(controller, engine)
    fill = gateway.execute(
        PaperOrderRequest("ABC", OrderSide.BUY, Decimal("10"), client_order_id="int-1"),
        Decimal("100"),
    )
    ledger = PortfolioLedger()
    ledger.apply_fill(fill.symbol, Side.BUY, fill.quantity, fill.price)
    assert ledger.position("ABC").quantity == Decimal("10")
    assert ledger.unrealized_pnl("ABC", Decimal("110")) == Decimal("100")
