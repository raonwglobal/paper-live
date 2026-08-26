from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    side: str
    quantity: Decimal
    order_type: str = "market"

@dataclass(frozen=True)
class OrderResult:
    broker: str
    order_id: str
    accepted: bool
    message: str = ""

class BrokerAdapter(Protocol):
    name: str
    def submit(self, request: OrderRequest) -> OrderResult: ...
    def cancel(self, order_id: str) -> bool: ...

class LiveBrokerDenied(PermissionError):
    pass
