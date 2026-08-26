from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .orchestrator_v2 import TradingGraph
from .execution import ExecutionGateway, OrderRequest, OrderSide
from .risk import RiskGuardian
from .reflection import EpisodicMemory, SelfReflectionWorker
from .state_machine import CycleState

@dataclass(frozen=True)
class PipelineResult:
    symbol: str
    action: str
    lifecycle: CycleState
    executed: bool
    pnl: Decimal

class TradingPipeline:
    def __init__(self, gateway: ExecutionGateway, risk: RiskGuardian, memory: EpisodicMemory | None = None):
        self.graph = TradingGraph()
        self.gateway = gateway
        self.risk = risk
        self.reflection = SelfReflectionWorker(memory or EpisodicMemory())

    def run(self, symbol: str, market: dict[str, Any], quantity: Decimal, price: Decimal) -> PipelineResult:
        result = self.graph.analyze(symbol, market)
        action = result.state.decision.get("action", "HOLD")
        if action == "HOLD":
            result.lifecycle = CycleState.REJECTED
            self.reflection.reflect(symbol, action, 0)
            return PipelineResult(symbol, action, CycleState.REFLECTED, False, Decimal("0"))
        side = OrderSide.BUY if action == "BUY" else OrderSide.SELL
        order = OrderRequest(symbol, side, quantity, client_order_id=f"pipeline-{symbol}")
        try:
            self.risk.approve(order, price)
            result.lifecycle = CycleState.RISK_APPROVED
            self.gateway.execute(order, price)
            result.lifecycle = CycleState.EXECUTED
            pnl = Decimal("0")
            self.reflection.reflect(symbol, action, float(pnl))
            return PipelineResult(symbol, action, CycleState.REFLECTED, True, pnl)
        except (PermissionError, ValueError):
            result.lifecycle = CycleState.REJECTED
            self.reflection.reflect(symbol, action, 0)
            return PipelineResult(symbol, action, CycleState.REFLECTED, False, Decimal("0"))
