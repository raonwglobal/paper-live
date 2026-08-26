from __future__ import annotations
from .protocol import BrokerAdapter, OrderRequest, OrderResult, LiveBrokerDenied

class BrokerRouter:
    def __init__(self, adapters: dict[str, BrokerAdapter]):
        self.adapters = dict(adapters)

    def submit(self, mode: str, broker: str, request: OrderRequest) -> OrderResult:
        if mode != "REAL_LIVE":
            raise LiveBrokerDenied("broker adapters are unavailable outside REAL_LIVE")
        adapter = self.adapters.get(broker)
        if adapter is None:
            raise LiveBrokerDenied(f"broker adapter is not configured: {broker}")
        return adapter.submit(request)

    def cancel(self, mode: str, broker: str, order_id: str) -> bool:
        if mode != "REAL_LIVE":
            raise LiveBrokerDenied("broker adapters are unavailable outside REAL_LIVE")
        adapter = self.adapters.get(broker)
        if adapter is None:
            raise LiveBrokerDenied(f"broker adapter is not configured: {broker}")
        return adapter.cancel(order_id)
