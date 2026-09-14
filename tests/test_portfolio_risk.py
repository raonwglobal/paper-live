from decimal import Decimal

import pytest

from paper_live.environment import EnvironmentController, ExecutionEnvironmentMode
from paper_live.execution import OrderSide, PaperAccount, PaperOrderRequest
from paper_live.risk import PortfolioRiskContext, RiskGuardian, RiskLimits


def guardian(*, cash: str = "1000000", limits: RiskLimits | None = None) -> RiskGuardian:
    controller = EnvironmentController(ExecutionEnvironmentMode.PAPER_SANDBOX)
    return RiskGuardian(controller, PaperAccount(Decimal(cash)), limits)


def order(quantity: str = "100") -> PaperOrderRequest:
    return PaperOrderRequest("AAA", OrderSide.BUY, Decimal(quantity))


def context(**kwargs: str) -> PortfolioRiskContext:
    values = {"account_value": "1000000", "portfolio_notional": "200000", "market_notional": "100000", "market": "KRX"}
    values.update(kwargs)
    return PortfolioRiskContext(**{key: Decimal(value) if key != "market" else value for key, value in values.items()})


def test_portfolio_risk_blocks_total_exposure() -> None:
    risk = guardian(limits=RiskLimits(max_portfolio_notional=Decimal("250000")))
    with pytest.raises(PermissionError, match="portfolio notional"):
        risk.approve_portfolio(order("100"), Decimal("1000"), context())


def test_portfolio_risk_blocks_market_concentration() -> None:
    risk = guardian(limits=RiskLimits(max_market_exposure=Decimal("0.20")))
    with pytest.raises(PermissionError, match="market exposure"):
        risk.approve_portfolio(order("150"), Decimal("1000"), context())


def test_portfolio_risk_blocks_cash_reserve() -> None:
    risk = guardian(cash="250000", limits=RiskLimits(min_cash_reserve=Decimal("0.10")))
    with pytest.raises(PermissionError, match="cash reserve"):
        risk.approve_portfolio(order("200"), Decimal("1000"), context(account_value="250000", portfolio_notional="0", market_notional="0"))


def test_portfolio_risk_allows_sell_that_reduces_exposure() -> None:
    risk = guardian(limits=RiskLimits(max_market_exposure=Decimal("0.20")))
    sell = PaperOrderRequest("AAA", OrderSide.SELL, Decimal("50"))
    risk.account.positions["AAA"] = Decimal("100")
    risk.approve_portfolio(sell, Decimal("1000"), context(market_notional="200000"))
