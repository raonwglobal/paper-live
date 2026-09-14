from decimal import Decimal

from paper_live.trade_facade import InternalTradeFacade


def test_portfolio_row_builds_delta_order_intent() -> None:
    row = {"symbol": "005930", "target_weight": 0.25, "close": 100}
    intent = InternalTradeFacade.intent_from_portfolio_row(
        row,
        account_value=Decimal("10000"),
        current_quantity=Decimal("10"),
    )

    assert intent is not None
    assert intent.symbol == "005930"
    assert intent.side == "BUY"
    assert intent.quantity == Decimal("15")
    assert intent.order_type == "MARKET"
    assert intent.price is None


def test_portfolio_row_builds_sell_delta_and_limit_price() -> None:
    row = {"symbol": "AAPL", "target_weight": 0.10, "close": 100}
    intent = InternalTradeFacade.intent_from_portfolio_row(
        row,
        account_value=Decimal("10000"),
        current_quantity=Decimal("20"),
        order_type="LIMIT",
    )

    assert intent is not None
    assert intent.side == "SELL"
    assert intent.quantity == Decimal("10")
    assert intent.price == Decimal("100")


def test_portfolio_row_returns_none_when_already_at_target() -> None:
    row = {"symbol": "MSFT", "target_weight": 0.20, "close": 100}
    intent = InternalTradeFacade.intent_from_portfolio_row(
        row,
        account_value=Decimal("10000"),
        current_quantity=Decimal("20"),
    )
    assert intent is None
