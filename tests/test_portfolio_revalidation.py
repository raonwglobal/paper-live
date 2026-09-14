from decimal import Decimal

import pytest

from paper_live.environment import EnvironmentController
from paper_live.execution import ExecutionGateway, PaperAccount, VirtualMatchingEngine
from paper_live.risk import RiskGuardian, RiskLimits
from paper_live.trade_facade import InternalTradeFacade


def _facade(account: PaperAccount, *, limits: RiskLimits | None = None) -> InternalTradeFacade:
    controller = EnvironmentController()
    engine = VirtualMatchingEngine(account, slippage_bps=Decimal("0"))
    gateway = ExecutionGateway(controller, engine)
    risk = RiskGuardian(controller, account, limits or RiskLimits())
    return InternalTradeFacade(controller=controller, risk=risk, gateway=gateway)


def test_revalidation_resizes_using_latest_price_not_recommendation_price():
    account = PaperAccount(Decimal("100000"))
    facade = _facade(account)
    row = {"symbol": "005930", "target_weight": "0.50", "close": "100"}

    result = facade.revalidate_portfolio_row(row, account=account, latest_prices={"005930": Decimal("200")})

    assert result.snapshot.context.account_value == Decimal("100000")
    assert result.intent is not None
    assert result.intent.quantity == Decimal("250")
    assert result.preview is not None
    assert result.preview.risk.approved is True
    assert result.preview.estimated_notional == Decimal("50000")


def test_revalidation_uses_latest_cash_and_rejects_cash_reserve_breach():
    account = PaperAccount(Decimal("10000"))
    facade = _facade(account)
    row = {"symbol": "005930", "target_weight": "0.80", "close": "100"}

    result = facade.revalidate_portfolio_row(row, account=account, latest_prices={"005930": Decimal("100")})

    assert result.intent is not None
    assert result.preview is not None
    assert result.preview.risk.approved is False
    assert any("cash reserve" in violation for violation in result.preview.risk.violations)


def test_revalidation_rebuilds_current_market_exposure_before_approval():
    account = PaperAccount(Decimal("100000"), {"000001": Decimal("600")})
    facade = _facade(account)
    row = {"symbol": "005930", "target_weight": "0.50", "close": "100"}

    result = facade.revalidate_portfolio_row(
        row,
        account=account,
        latest_prices={"000001": Decimal("100"), "005930": Decimal("100")},
        markets={"000001": "KRX", "005930": "KRX"},
    )

    assert result.snapshot.context.portfolio_notional == Decimal("60000")
    assert result.intent is not None
    assert result.preview is not None
    assert result.preview.risk.approved is False
    assert any("market exposure" in violation for violation in result.preview.risk.violations)


def test_revalidation_fails_closed_when_target_latest_price_is_missing_or_invalid():
    account = PaperAccount(Decimal("100000"))
    facade = _facade(account)
    row = {"symbol": "005930", "target_weight": "0.50", "close": "100"}

    with pytest.raises(ValueError, match="missing latest price"):
        facade.revalidate_portfolio_row(row, account=account, latest_prices={})
    with pytest.raises(ValueError, match="latest price must be positive"):
        facade.revalidate_portfolio_row(row, account=account, latest_prices={"005930": Decimal("0")})


def test_revalidation_uses_latest_price_for_limit_order():
    account = PaperAccount(Decimal("100000"))
    facade = _facade(account)
    row = {"symbol": "005930", "target_weight": "0.20", "close": "100"}

    result = facade.revalidate_portfolio_row(
        row,
        account=account,
        latest_prices={"005930": Decimal("250")},
        order_type="LIMIT",
    )

    assert result.intent is not None
    assert result.intent.price == Decimal("250")
    assert result.preview is not None
    assert result.preview.estimated_notional == Decimal("20000")
