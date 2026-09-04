from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True)
class Position:
    symbol: str
    quantity: Decimal
    average_price: Decimal
    realized_pnl: Decimal = Decimal("0")


class PortfolioLedger:
    def __init__(self):
        self._positions: dict[str, Position] = {}

    def apply_fill(self, symbol: str, side: Side, quantity: Decimal, price: Decimal) -> Position:
        if quantity <= 0 or price <= 0:
            raise ValueError("quantity and price must be positive")
        current = self._positions.get(symbol, Position(symbol, Decimal("0"), Decimal("0")))
        if side is Side.BUY:
            total_cost = current.average_price * current.quantity + price * quantity
            new_qty = current.quantity + quantity
            avg = total_cost / new_qty
            updated = Position(symbol, new_qty, avg, current.realized_pnl)
        else:
            if quantity > current.quantity:
                raise ValueError("sell quantity exceeds position")
            realized = current.realized_pnl + (price - current.average_price) * quantity
            new_qty = current.quantity - quantity
            avg = Decimal("0") if new_qty == 0 else current.average_price
            updated = Position(symbol, new_qty, avg, realized)
        self._positions[symbol] = updated
        return updated

    def position(self, symbol: str) -> Position:
        return self._positions.get(symbol, Position(symbol, Decimal("0"), Decimal("0")))

    def unrealized_pnl(self, symbol: str, mark_price: Decimal) -> Decimal:
        p = self.position(symbol)
        if mark_price <= 0:
            raise ValueError("mark_price must be positive")
        return (mark_price - p.average_price) * p.quantity

    def total_pnl(self, symbol: str, mark_price: Decimal) -> Decimal:
        p = self.position(symbol)
        return p.realized_pnl + self.unrealized_pnl(symbol, mark_price)
