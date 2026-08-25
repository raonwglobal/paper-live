from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class BrokerOrderResult:
    broker: str
    broker_order_id: str
    status: str


class BrokerAdapter(ABC):
    name: str

    @abstractmethod
    def submit(self, symbol: str, side: str, quantity: Decimal, price: Decimal | None = None) -> BrokerOrderResult:
        raise NotImplementedError


class TossBrokerAdapter(BrokerAdapter):
    name = "toss"

    def submit(self, symbol: str, side: str, quantity: Decimal, price: Decimal | None = None) -> BrokerOrderResult:
        raise NotImplementedError("Live Toss broker adapter is disabled until credentials, API contract and live approval are configured")


class KBBrokerAdapter(BrokerAdapter):
    name = "kb"

    def submit(self, symbol: str, side: str, quantity: Decimal, price: Decimal | None = None) -> BrokerOrderResult:
        raise NotImplementedError("Live KB broker adapter is disabled until credentials, API contract and live approval are configured")
