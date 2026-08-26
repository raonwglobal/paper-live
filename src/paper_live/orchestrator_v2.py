from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from .agents import AgentState, MacroRegimeAgent, FundamentalAnalystAgent, TechnicalVisionAgent, SentimentQuantAgent, DebateOrchestratorAgent
from .state_machine import CycleState, CycleStateMachine

@dataclass
class GraphCycleResult:
    state: AgentState
    lifecycle: CycleState

class TradingGraph:
    """Graph-style orchestration with explicit lifecycle transitions."""
    def __init__(self):
        self.nodes = {"macro": MacroRegimeAgent(), "fundamental": FundamentalAnalystAgent(), "technical": TechnicalVisionAgent(), "sentiment": SentimentQuantAgent(), "debate": DebateOrchestratorAgent()}
    def analyze(self, symbol: str, market: dict[str, Any]) -> GraphCycleResult:
        state = AgentState(symbol=symbol, market=market)
        lifecycle = CycleStateMachine()
        for name in ("macro", "fundamental", "technical", "sentiment"):
            state = self.nodes[name].run(state)
        lifecycle.advance(CycleState.ANALYZED)
        state = self.nodes["debate"].run(state)
        lifecycle.advance(CycleState.DEBATED)
        return GraphCycleResult(state, lifecycle.state)
