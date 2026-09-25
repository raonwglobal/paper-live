from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping

from .execution import PaperAccount
from .risk import PortfolioRiskContext


@dataclass(frozen=True)
class PositionValuation:
    symbol: str
    quantity: Decimal
    price: Decimal
    market: str
    notional: Decimal


@dataclass(frozen=True)
class PortfolioRiskSnapshot:
    context: PortfolioRiskContext
    cash: Decimal
    cash_ratio: Decimal
    positions: tuple[PositionValuation, ...]
    market_notionals: Mapping[str, Decimal]


class PortfolioRiskContextBuilder:
    """Build deterministic portfolio exposure from account positions and prices.

    Missing or invalid prices fail closed rather than silently understating risk.
    """

    def build(
        self,
        account: PaperAccount,
        prices: Mapping[str, Decimal],
        *,
        markets: Mapping[str, str] | None = None,
        target_symbol: str | None = None,
    ) -> PortfolioRiskSnapshot:
        if account.cash < 0:
            raise ValueError("account cash must be non-negative")
        market_map = markets or {}
        valuations: list[PositionValuation] = []
        market_notionals: dict[str, Decimal] = {}
        portfolio_notional = Decimal("0")

        for symbol, quantity in account.positions.items():
            if quantity < 0:
                raise ValueError(f"position quantity must be non-negative: {symbol}")
            if quantity == 0:
                continue
            raw_price = prices.get(symbol)
            if raw_price is None:
                raise ValueError(f"missing price for held position: {symbol}")
            price = Decimal(str(raw_price))
            if price <= 0:
                raise ValueError(f"price must be positive: {symbol}")
            notional = quantity * price
            market = str(market_map.get(symbol, "UNKNOWN")).strip() or "UNKNOWN"
            valuations.append(PositionValuation(symbol, quantity, price, market, notional))
            portfolio_notional += notional
            market_notionals[market] = market_notionals.get(market, Decimal("0")) + notional

        account_value = account.cash + portfolio_notional
        if account_value <= 0:
            raise ValueError("account value must be positive")

        selected_market = ""
        selected_market_notional = Decimal("0")
        if target_symbol:
            selected_market = str(market_map.get(target_symbol, "UNKNOWN")).strip() or "UNKNOWN"
            selected_market_notional = market_notionals.get(selected_market, Decimal("0"))

        context = PortfolioRiskContext(
            account_value=account_value,
            portfolio_notional=portfolio_notional,
            market_notional=selected_market_notional,
            market=selected_market,
        )
        return PortfolioRiskSnapshot(
            context=context,
            cash=account.cash,
            cash_ratio=account.cash / account_value,
            positions=tuple(valuations),
            market_notionals=dict(market_notionals),
        )
