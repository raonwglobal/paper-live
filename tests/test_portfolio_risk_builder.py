from decimal import Decimal

import pytest

from paper_live.execution import PaperAccount
from paper_live.portfolio_risk import PortfolioRiskContextBuilder


def test_builder_values_portfolio_and_market_exposure() -> None:
    account = PaperAccount(
        Decimal("400000"),
        {"AAA": Decimal("100"), "BBB": Decimal("50"), "ZERO": Decimal("0")},
    )
    snapshot = PortfolioRiskContextBuilder().build(
        account,
        {"AAA": Decimal("1000"), "BBB": Decimal("2000")},
        markets={"AAA": "KR", "BBB": "US"},
        target_symbol="AAA",
    )
    assert snapshot.context.portfolio_notional == Decimal("200000")
    assert snapshot.context.account_value == Decimal("600000")
    assert snapshot.context.market_notional == Decimal("100000")
    assert snapshot.cash_ratio == Decimal("2") / Decimal("3")
    assert snapshot.market_notionals == {"KR": Decimal("100000"), "US": Decimal("100000")}


def test_builder_fails_closed_when_held_price_is_missing() -> None:
    account = PaperAccount(Decimal("100000"), {"AAA": Decimal("10")})
    with pytest.raises(ValueError, match="missing price"):
        PortfolioRiskContextBuilder().build(account, {})


def test_builder_rejects_invalid_position() -> None:
    account = PaperAccount(Decimal("100000"), {"AAA": Decimal("-1")})
    with pytest.raises(ValueError, match="non-negative"):
        PortfolioRiskContextBuilder().build(account, {"AAA": Decimal("1000")})
