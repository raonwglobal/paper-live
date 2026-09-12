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
