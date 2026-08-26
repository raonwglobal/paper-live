from __future__ import annotations
from dataclasses import dataclass, replace
from enum import Enum
from decimal import Decimal

class OrderStatus(str, Enum):
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"

@dataclass(frozen=True)
class OrderRecord:
    client_order_id: str
    symbol: str
    side: str
    quantity: Decimal
    filled_quantity: Decimal = Decimal("0")
    status: OrderStatus = OrderStatus.NEW

class OrderLifecycle:
    def __init__(self) -> None:
        self._orders: dict[str, OrderRecord] = {}

    def submit(self, order: OrderRecord) -> OrderRecord:
        existing = self._orders.get(order.client_order_id)
        if existing is not None:
            if existing != order:
                raise ValueError("client_order_id already used with different order")
            return existing
        self._orders[order.client_order_id] = order
        return order

    def fill(self, client_order_id: str, quantity: Decimal) -> OrderRecord:
        current = self._get(client_order_id)
        if quantity <= 0 or current.filled_quantity + quantity > current.quantity:
            raise ValueError("invalid fill quantity")
        filled = current.filled_quantity + quantity
        status = OrderStatus.FILLED if filled == current.quantity else OrderStatus.PARTIALLY_FILLED
        updated = replace(current, filled_quantity=filled, status=status)
        self._orders[client_order_id] = updated
        return updated

    def cancel(self, client_order_id: str) -> OrderRecord:
        current = self._get(client_order_id)
        if current.status in {OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED}:
            return current
        updated = replace(current, status=OrderStatus.CANCELED)
        self._orders[client_order_id] = updated
        return updated

    def get(self, client_order_id: str) -> OrderRecord | None:
        return self._orders.get(client_order_id)

    def _get(self, client_order_id: str) -> OrderRecord:
        current = self.get(client_order_id)
        if current is None:
            raise KeyError(client_order_id)
        return current
