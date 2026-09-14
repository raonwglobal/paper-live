from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from threading import Lock

from .environment import EnvironmentController, ExecutionEnvironmentMode
from .execution import OrderSide, PaperAccount, PaperOrderRequest


@dataclass(frozen=True)
class RiskLimits:
    max_order_notional: Decimal = Decimal("1000000")
    max_position_notional: Decimal = Decimal("5000000")
    max_daily_loss: Decimal = Decimal("500000")
    max_portfolio_notional: Decimal = Decimal("10000000")
    max_market_exposure: Decimal = Decimal("0.50")
    min_cash_reserve: Decimal = Decimal("0.10")

    def __post_init__(self) -> None:
        if any(value < 0 for value in (self.max_order_notional, self.max_position_notional, self.max_daily_loss, self.max_portfolio_notional)):
            raise ValueError("notional risk limits must be non-negative")
        if not 0 <= self.max_market_exposure <= 1:
            raise ValueError("max_market_exposure must be between 0 and 1")
        if not 0 <= self.min_cash_reserve <= 1:
            raise ValueError("min_cash_reserve must be between 0 and 1")


@dataclass(frozen=True)
class PortfolioRiskContext:
    """Current portfolio valuation used by the portfolio-level risk gate."""

    account_value: Decimal
    portfolio_notional: Decimal
    market_notional: Decimal = Decimal("0")
    market: str = ""


class CircuitBreaker:
    def __init__(self) -> None:
        self._tripped = False
        self._lock = Lock()

    def trip(self) -> None:
        with self._lock:
            self._tripped = True

    def reset(self) -> None:
        with self._lock:
            self._tripped = False

    @property
    def tripped(self) -> bool:
        with self._lock:
            return self._tripped


class RiskGuardian:
    """Deterministic pre-trade gate; never creates or modifies orders."""

    def __init__(self, controller: EnvironmentController, account: PaperAccount, limits: RiskLimits | None = None):
        self.controller = controller
        self.account = account
        self.limits = limits or RiskLimits()
        self.circuit_breaker = CircuitBreaker()
        self.daily_pnl = Decimal("0")

    def approve(self, order: PaperOrderRequest, reference_price: Decimal) -> None:
        if self.circuit_breaker.tripped:
            raise PermissionError("circuit breaker is active")
        if order.quantity <= 0 or reference_price <= 0:
            raise ValueError("invalid order")
        notional = order.quantity * reference_price
        if notional > self.limits.max_order_notional:
            raise PermissionError("order notional exceeds risk limit")
        if self.daily_pnl <= -self.limits.max_daily_loss:
            raise PermissionError("daily loss limit exceeded")

        current_position = self.account.positions.get(order.symbol, Decimal("0"))
        projected = (
            current_position + order.quantity if order.side == OrderSide.BUY else current_position - order.quantity
        )
        if projected < 0:
            raise PermissionError("sell quantity exceeds current position")
        if projected * reference_price > self.limits.max_position_notional:
            raise PermissionError("position notional exceeds risk limit")

        if self.controller.get_current_mode() == ExecutionEnvironmentMode.REAL_LIVE:
            self.controller.assert_skill_allowed("skill-risk-circuit-breaker")

    def approve_portfolio(
        self,
        order: PaperOrderRequest,
        reference_price: Decimal,
        context: PortfolioRiskContext,
    ) -> None:
        """Apply portfolio-level exposure, market concentration and cash-reserve gates."""
        self.approve(order, reference_price)
        if context.account_value <= 0 or context.portfolio_notional < 0 or context.market_notional < 0:
            raise ValueError("invalid portfolio risk context")
        order_notional = order.quantity * reference_price
        projected_portfolio = context.portfolio_notional + (order_notional if order.side is OrderSide.BUY else -order_notional)
        if projected_portfolio < 0:
            raise PermissionError("projected portfolio exposure is negative")
        if projected_portfolio > self.limits.max_portfolio_notional:
            raise PermissionError("portfolio notional exceeds risk limit")
        if context.account_value > 0:
            projected_market = context.market_notional + (order_notional if order.side is OrderSide.BUY else -order_notional)
            if projected_market < 0:
                raise PermissionError("projected market exposure is negative")
            if projected_market / context.account_value > self.limits.max_market_exposure:
                raise PermissionError("market exposure exceeds risk limit")
            if order.side is OrderSide.BUY:
                projected_cash = self.account.cash - order_notional
                if projected_cash / context.account_value < self.limits.min_cash_reserve:
                    raise PermissionError("cash reserve would fall below risk limit")
