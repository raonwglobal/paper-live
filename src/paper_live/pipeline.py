from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import uuid4

from .orchestrator_v2 import TradingGraph
from .execution import ExecutionGateway, OrderRequest, OrderSide
from .risk import RiskGuardian
from .reflection import EpisodicMemory, SelfReflectionWorker, TradeEpisode
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

    def _reflect(self, symbol: str, action: str, price: Decimal, pnl: Decimal, market: dict[str, Any]) -> None:
        episode = TradeEpisode(
            episode_id=str(uuid4()),
            symbol=symbol,
            action=action,
            entry_price=str(price),
            exit_price=str(price),
            pnl=str(pnl),
            decision_context=market,
            outcome="EXECUTED" if pnl != 0 else "FLAT",
            created_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        )
        self.reflection.reflect(episode)

    def run(self, symbol: str, market: dict[str, Any], quantity: Decimal, price: Decimal) -> PipelineResult:
        result = self.graph.analyze(symbol, market)
        action = result.state.decision.get("action", "HOLD")
        if action == "HOLD":
            self._reflect(symbol, action, price, Decimal("0"), market)
            return PipelineResult(symbol, action, CycleState.REFLECTED, False, Decimal("0"))
        side = OrderSide.BUY if action == "BUY" else OrderSide.SELL
        order = OrderRequest(symbol, side, quantity, client_order_id=f"pipeline-{symbol}-{uuid4().hex[:8]}")
        try:
            self.risk.approve(order, price)
            self.gateway.execute(order, price)
            pnl = Decimal("0")
            self._reflect(symbol, action, price, pnl, market)
            return PipelineResult(symbol, action, CycleState.REFLECTED, True, pnl)
        except (PermissionError, ValueError):
            self._reflect(symbol, action, price, Decimal("0"), market)
            return PipelineResult(symbol, action, CycleState.REFLECTED, False, Decimal("0"))
