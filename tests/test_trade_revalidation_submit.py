from decimal import Decimal

import pytest

from paper_live.environment import EnvironmentController
from paper_live.execution import ExecutionGateway, Fill, PaperAccount, VirtualMatchingEngine
from paper_live.risk import RiskGuardian, RiskLimits
from paper_live.trade_facade import InternalTradeFacade


def _facade(cash: str = "1000000", limits: RiskLimits | None = None):
    account = PaperAccount(Decimal(cash))
    controller = EnvironmentController()
    gateway = ExecutionGateway(controller, VirtualMatchingEngine(account, slippage_bps=Decimal("0")))
    facade = InternalTradeFacade(controller, RiskGuardian(controller, account, limits or RiskLimits()))
    return facade, account


def test_revalidation_uses_latest_price_for_sizing():
    facade, account = _facade()
    row = {"symbol": "005930", "target_weight": 0.10, "close": 100}

    result = facade.revalidate_portfolio_row(row, account=account, latest_prices={"005930": Decimal("200")})

    assert result.intent is not None
    assert result.intent.quantity == Decimal("500")
    assert result.preview is not None
    assert result.preview.estimated_notional == Decimal("100000")


def test_revalidated_submit_does_not_reuse_stale_preview():
    facade, account = _facade()
    row = {"symbol": "005930", "target_weight": 0.10, "close": 100}
    stale = facade.preview_portfolio_row(row, account=account, prices={"005930": Decimal("100")})
    assert stale is not None
    assert stale.intent.quantity == Decimal("1000")

    result = facade.submit_portfolio_row_revalidated(row, account=account, latest_prices={"005930": Decimal("200")})

    assert isinstance(result, Fill)
    assert result.quantity == Decimal("500")
    assert account.positions["005930"] == Decimal("500")


def test_revalidated_submit_fails_closed_when_latest_price_missing():
    facade, account = _facade()
    row = {"symbol": "005930", "target_weight": 0.10, "close": 100}

    with pytest.raises(ValueError, match="missing latest price"):
        facade.submit_portfolio_row_revalidated(row, account=account, latest_prices={})


def test_revalidated_submit_rechecks_current_cash_reserve():
    limits = RiskLimits(min_cash_reserve=Decimal("0.50"))
    facade, account = _facade(cash="100000", limits=limits)
    row = {"symbol": "005930", "target_weight": 0.80, "close": 100}

    result = facade.revalidate_portfolio_row(row, account=account, latest_prices={"005930": Decimal("100")})

    assert result.preview is not None
    assert result.preview.risk.approved is False
    assert result.preview.risk.violations
