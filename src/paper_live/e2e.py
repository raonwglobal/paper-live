from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .agents import AgentState, DebateOrchestratorAgent, MacroRegimeAgent, FundamentalAnalystAgent, TechnicalVisionAgent, SentimentQuantAgent
from .execution import ExecutionGateway, OrderRequest, OrderSide
from .risk import RiskGuardian


@dataclass
class PaperCycleResult:
    symbol: str
    action: str
    approved: bool
    event_count: int


class PaperTradingCycle:
    """Single deterministic market->decision->risk->paper execution cycle."""

    def __init__(self, gateway: ExecutionGateway, risk: RiskGuardian):
        self.gateway = gateway
        self.risk = risk
        self.signal_agents = [MacroRegimeAgent(), FundamentalAnalystAgent(), TechnicalVisionAgent(), SentimentQuantAgent()]
        self.debate = DebateOrchestratorAgent()

    def run(self, symbol: str, market: dict[str, Any], quantity: Decimal, price: Decimal) -> PaperCycleResult:
        state = AgentState(symbol=symbol, market=market)
        for agent in self.signal_agents:
            state = agent.run(state)
        state = self.debate.run(state)
        action = state.decision.get("action", "HOLD")
        if action == "HOLD":
            state.events.append({"type": "ORDER_SKIPPED", "reason": "HOLD"})
            return PaperCycleResult(symbol, action, True, len(state.events))
        side = OrderSide.BUY if action == "BUY" else OrderSide.SELL
        order = OrderRequest(symbol, side, quantity, client_order_id=f"paper-{symbol}")
        try:
            self.risk.approve(order, price)
            fill = self.gateway.execute(order, price)
            state.events.append({"type": "ORDER_FILLED", "fill": fill})
            return PaperCycleResult(symbol, action, True, len(state.events))
        except (PermissionError, ValueError):
            state.events.append({"type": "ORDER_REJECTED"})
            return PaperCycleResult(symbol, action, False, len(state.events))
