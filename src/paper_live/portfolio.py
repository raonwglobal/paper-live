from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from math import sqrt

from .execution import PaperAccount


@dataclass(frozen=True)
class PortfolioSnapshot:
    cash: Decimal
    market_value: Decimal
    equity: Decimal


def snapshot(account: PaperAccount, prices: dict[str, Decimal]) -> PortfolioSnapshot:
    market_value = sum((qty * prices.get(symbol, Decimal("0")) for symbol, qty in account.positions.items()), Decimal("0"))
    return PortfolioSnapshot(account.cash, market_value, account.cash + market_value)


def sharpe(returns: list[Decimal], periods_per_year: int = 252) -> Decimal:
    if len(returns) < 2:
        return Decimal("0")
    mean = sum(returns, Decimal("0")) / Decimal(len(returns))
    variance = sum((r - mean) ** 2 for r in returns) / Decimal(len(returns) - 1)
    if variance <= 0:
        return Decimal("0")
    return mean / Decimal(str(sqrt(float(variance)))) * Decimal(str(sqrt(periods_per_year)))


def max_drawdown(equities: list[Decimal]) -> Decimal:
    peak = Decimal("0")
    worst = Decimal("0")
    for equity in equities:
        peak = max(peak, equity)
        if peak > 0:
            worst = max(worst, (peak - equity) / peak)
    return worst
