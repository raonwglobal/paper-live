from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class AgentState:
    symbol: str
    market: dict[str, Any] = field(default_factory=dict)
    signals: dict[str, Any] = field(default_factory=dict)
    decision: dict[str, Any] = field(default_factory=dict)
    risk: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)


class Agent:
    name = "agent"

    def run(self, state: AgentState) -> AgentState:
        raise NotImplementedError


class MacroRegimeAgent(Agent):
    name = "macro-regime"
    def run(self, state: AgentState) -> AgentState:
        state.signals["macro"] = state.market.get("macro_regime", "UNKNOWN")
        return state


class FundamentalAnalystAgent(Agent):
    name = "fundamental"
    def run(self, state: AgentState) -> AgentState:
        state.signals["fundamental"] = state.market.get("fundamental_signal", "NEUTRAL")
        return state


class TechnicalVisionAgent(Agent):
    name = "technical-vision"
    def run(self, state: AgentState) -> AgentState:
        state.signals["technical"] = state.market.get("technical_signal", "NEUTRAL")
        return state


class SentimentQuantAgent(Agent):
    name = "sentiment"
    def run(self, state: AgentState) -> AgentState:
        state.signals["sentiment"] = state.market.get("sentiment_signal", "NEUTRAL")
        return state


class DebateOrchestratorAgent(Agent):
    name = "debate-orchestrator"
    _signal_keys = ("macro_regime", "fundamental_signal", "technical_signal", "sentiment_signal")

    def run(self, state: AgentState) -> AgentState:
        values = list(state.signals.values()) or [state.market.get(k, "NEUTRAL") for k in self._signal_keys]
        bullish = sum(v in {"BUY", "BULLISH", "POSITIVE"} for v in values)
        bearish = sum(v in {"SELL", "BEARISH", "NEGATIVE"} for v in values)
        action = "BUY" if bullish > bearish else "SELL" if bearish > bullish else "HOLD"
        state.decision = {"action": action, "bullish": bullish, "bearish": bearish}
        return state


class RiskGuardianAgent(Agent):
    name = "risk-guardian"
    def __init__(self, approve: Callable[[dict[str, Any]], None]):
        self._approve = approve
    def run(self, state: AgentState) -> AgentState:
        self._approve(state.decision)
        state.risk["approved"] = True
        return state


class ExecutionTraderAgent(Agent):
    name = "execution-trader"
    def __init__(self, execute: Callable[[dict[str, Any]], Any]):
        self._execute = execute
    def run(self, state: AgentState) -> AgentState:
        if state.decision.get("action") == "HOLD":
            state.events.append({"type": "ORDER_SKIPPED", "reason": "HOLD"})
            return state
        result = self._execute(state.decision)
        state.events.append({"type": "ORDER_EXECUTED", "result": result})
        return state
