from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from .agents import (
    AgentState,
    DebateOrchestratorAgent,
    FundamentalAnalystAgent,
    MacroRegimeAgent,
    SentimentQuantAgent,
    TechnicalVisionAgent,
)
from .state_machine import CycleState, CycleStateMachine


class GraphState(TypedDict):
    symbol: str
    market: dict[str, Any]
    signals: dict[str, Any]
    decision: dict[str, Any]
    risk: dict[str, Any]
    events: list[dict[str, Any]]


@dataclass
class GraphCycleResult:
    state: AgentState
    lifecycle: CycleState


class TradingGraph:
    """LangGraph StateGraph orchestration for deterministic agent boundaries."""

    def __init__(self):
        self.nodes = {
            "macro": MacroRegimeAgent(),
            "fundamental": FundamentalAnalystAgent(),
            "technical": TechnicalVisionAgent(),
            "sentiment": SentimentQuantAgent(),
            "debate": DebateOrchestratorAgent(),
        }
        builder = StateGraph(GraphState)
        builder.add_node("macro", self._node("macro"))
        builder.add_node("fundamental", self._node("fundamental"))
        builder.add_node("technical", self._node("technical"))
        builder.add_node("sentiment", self._node("sentiment"))
        builder.add_node("debate", self._node("debate"))
        builder.add_edge(START, "macro")
        builder.add_edge("macro", "fundamental")
        builder.add_edge("fundamental", "technical")
        builder.add_edge("technical", "sentiment")
        builder.add_edge("sentiment", "debate")
        builder.add_edge("debate", END)
        self.graph = builder.compile()

    def _node(self, name: str):
        agent = self.nodes[name]

        def invoke(data: GraphState) -> GraphState:
            state = AgentState(
                symbol=data["symbol"],
                market=dict(data.get("market", {})),
                signals=dict(data.get("signals", {})),
                decision=dict(data.get("decision", {})),
                risk=dict(data.get("risk", {})),
                events=list(data.get("events", [])),
            )
            updated = agent.run(state)
            return {
                "symbol": updated.symbol,
                "market": updated.market,
                "signals": updated.signals,
                "decision": updated.decision,
                "risk": updated.risk,
                "events": updated.events,
            }

        return invoke

    def analyze(self, symbol: str, market: dict[str, Any]) -> GraphCycleResult:
        initial: GraphState = {
            "symbol": symbol,
            "market": market,
            "signals": {},
            "decision": {},
            "risk": {},
            "events": [],
        }
        result = self.graph.invoke(initial)
        state = AgentState(**result)
        lifecycle = CycleStateMachine()
        lifecycle.advance(CycleState.ANALYZED)
        lifecycle.advance(CycleState.DEBATED)
        return GraphCycleResult(state, lifecycle.state)
