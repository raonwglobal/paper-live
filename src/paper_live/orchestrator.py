from __future__ import annotations

from dataclasses import dataclass, field

from .agents import Agent, AgentState


@dataclass
class StateGraph:
    nodes: list[Agent] = field(default_factory=list)

    def add_node(self, agent: Agent) -> StateGraph:
        self.nodes.append(agent)
        return self

    def run(self, state: AgentState) -> AgentState:
        for node in self.nodes:
            state.events.append({"type": "AGENT_STARTED", "agent": node.name})
            state = node.run(state)
            state.events.append({"type": "AGENT_COMPLETED", "agent": node.name})
        return state


def build_analysis_graph() -> StateGraph:
    from .agents import (
        DebateOrchestratorAgent,
        FundamentalAnalystAgent,
        MacroRegimeAgent,
        SentimentQuantAgent,
        TechnicalVisionAgent,
    )

    return StateGraph(
        [
            MacroRegimeAgent(),
            FundamentalAnalystAgent(),
            TechnicalVisionAgent(),
            SentimentQuantAgent(),
            DebateOrchestratorAgent(),
        ]
    )
