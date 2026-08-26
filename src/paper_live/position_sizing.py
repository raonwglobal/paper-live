from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal

@dataclass(frozen=True)
class PositionSizingConfig:
    risk_fraction: Decimal = Decimal("0.01")
    max_notional_fraction: Decimal = Decimal("0.20")
    min_quantity: Decimal = Decimal("1")

class PositionSizer:
    def __init__(self, config: PositionSizingConfig | None = None):
        self.config = config or PositionSizingConfig()

    def size(self, equity: Decimal, price: Decimal, stop_distance: Decimal) -> Decimal:
        if equity <= 0 or price <= 0 or stop_distance <= 0:
            raise ValueError("equity, price and stop_distance must be positive")
        risk_budget = equity * self.config.risk_fraction
        risk_qty = risk_budget / stop_distance
        notional_cap_qty = (equity * self.config.max_notional_fraction) / price
        quantity = min(risk_qty, notional_cap_qty)
        if quantity < self.config.min_quantity:
            return Decimal("0")
        return quantity.quantize(Decimal("0.000001"))
