from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from .execution import ExecutionGateway, OrderSide, PaperOrderRequest
from .orchestrator_v2 import TradingGraph
from .pnl import PortfolioLedger, Side
from .reflection import EpisodicMemory, SelfReflectionWorker, TradeEpisode
from .risk import RiskGuardian
from .state_machine import CycleState


@dataclass(frozen=True)
class PipelineResult:
    symbol: str
    action: str
    lifecycle: CycleState
    executed: bool
    pnl: Decimal


class TradingPipeline:
    def __init__(
        self,
        gateway: ExecutionGateway,
        risk: RiskGuardian,
        memory: EpisodicMemory | None = None,
        ledger: PortfolioLedger | None = None,
    ):
        self.graph = TradingGraph()
        self.gateway = gateway
        self.risk = risk
        self.ledger = ledger or PortfolioLedger()
        self.reflection = SelfReflectionWorker(memory or EpisodicMemory())

    def _reflect(
        self,
        symbol: str,
        action: str,
        entry_price: Decimal,
        exit_price: Decimal,
        pnl: Decimal,
        market: dict[str, Any],
        outcome: str,
    ) -> None:
        episode = TradeEpisode(
            episode_id=str(uuid4()),
            symbol=symbol,
            action=action,
            entry_price=str(entry_price),
            exit_price=str(exit_price),
            pnl=str(pnl),
            decision_context=market,
            outcome=outcome,
            created_at=datetime.now(UTC).isoformat(),
        )
        self.reflection.reflect(episode)

    def run(self, symbol: str, market: dict[str, Any], quantity: Decimal, price: Decimal) -> PipelineResult:
        result = self.graph.analyze(symbol, market)
        action = result.state.decision.get("action", "HOLD")
        if action == "HOLD":
            self._reflect(symbol, action, price, price, Decimal("0"), market, "HOLD")
            return PipelineResult(symbol, action, CycleState.REFLECTED, False, Decimal("0"))
        side = OrderSide.BUY if action == "BUY" else OrderSide.SELL
        order = PaperOrderRequest(symbol, side, quantity, client_order_id=f"pipeline-{symbol}-{uuid4().hex[:8]}")
        try:
            self.risk.approve(order, price)
            fill = self.gateway.execute(order, price)
            if fill.quantity <= 0 or fill.status == "REJECTED":
                self._reflect(symbol, action, price, price, Decimal("0"), market, "REJECTED")
                return PipelineResult(symbol, action, CycleState.REFLECTED, False, Decimal("0"))
            self.ledger.apply_fill(
                symbol, Side.BUY if fill.side is OrderSide.BUY else Side.SELL, fill.quantity, fill.price
            )
            pnl = self.ledger.total_pnl(symbol, fill.price)
            self._reflect(symbol, action, fill.price, fill.price, pnl, market, fill.status)
            return PipelineResult(symbol, action, CycleState.REFLECTED, True, pnl)
        except (PermissionError, ValueError):
            self._reflect(symbol, action, price, price, Decimal("0"), market, "REJECTED")
            return PipelineResult(symbol, action, CycleState.REFLECTED, False, Decimal("0"))
