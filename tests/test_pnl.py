from decimal import Decimal
import pytest
from paper_live.pnl import PortfolioLedger, Side

def test_average_cost_and_realized_pnl():
    p = PortfolioLedger()
    p.apply_fill("ABC", Side.BUY, Decimal("10"), Decimal("100"))
    p.apply_fill("ABC", Side.BUY, Decimal("10"), Decimal("120"))
    assert p.position("ABC").average_price == Decimal("110")
    p.apply_fill("ABC", Side.SELL, Decimal("5"), Decimal("130"))
    assert p.position("ABC").realized_pnl == Decimal("100")
    assert p.unrealized_pnl("ABC", Decimal("140")) == Decimal("300")
    assert p.total_pnl("ABC", Decimal("140")) == Decimal("400")

def test_cannot_sell_more_than_position():
    with pytest.raises(ValueError):
        PortfolioLedger().apply_fill("ABC", Side.SELL, Decimal("1"), Decimal("100"))
