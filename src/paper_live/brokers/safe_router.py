from __future__ import annotations
from .protocol import BrokerAdapter, BrokerOrderRequest, OrderResult, LiveBrokerDenied
from paper_live.security.live_approval_gate import LiveApprovalGate

class BrokerRouter:
    def __init__(self, adapters: dict[str, BrokerAdapter], approval_gate: LiveApprovalGate | None = None):
        self.adapters = dict(adapters)
        self.approval_gate = approval_gate

    def _authorize(self, mode: str, approval_id: str | None) -> None:
        if mode != "REAL_LIVE":
            raise LiveBrokerDenied("broker adapters are unavailable outside REAL_LIVE")
        if self.approval_gate is None or approval_id is None:
            raise LiveBrokerDenied("explicit live approval is required")
        self.approval_gate.require(approval_id)

    def submit(self, mode: str, broker: str, request: BrokerOrderRequest, approval_id: str | None = None) -> OrderResult:
        self._authorize(mode, approval_id)
        adapter = self.adapters.get(broker)
        if adapter is None:
            raise LiveBrokerDenied(f"broker adapter is not configured: {broker}")
        return adapter.submit(request)

    def cancel(self, mode: str, broker: str, order_id: str, approval_id: str | None = None) -> bool:
        self._authorize(mode, approval_id)
        adapter = self.adapters.get(broker)
        if adapter is None:
            raise LiveBrokerDenied(f"broker adapter is not configured: {broker}")
        return adapter.cancel(order_id)
