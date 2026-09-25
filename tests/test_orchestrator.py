from paper_live.orchestrator_v2 import TradingGraph
from paper_live.state_machine import CycleState


def test_graph_analyze_runs_signal_nodes_and_debate():
    result = TradingGraph().analyze(
        "ABC",
        {
            "macro_regime": "BULLISH",
            "fundamental_signal": "BUY",
            "technical_signal": "BUY",
            "sentiment_signal": "POSITIVE",
        },
    )
    assert result.state.decision["action"] == "BUY"
    assert result.lifecycle is CycleState.DEBATED
