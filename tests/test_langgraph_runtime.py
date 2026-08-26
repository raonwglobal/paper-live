from paper_live.orchestrator_v2 import TradingGraph
from paper_live.state_machine import CycleState

def test_trading_graph_compiles_and_runs_agent_chain():
    result = TradingGraph().analyze(
        "ABC",
        {"macro_regime": "BULLISH", "fundamental_signal": "BUY", "technical_signal": "BUY", "sentiment_signal": "POSITIVE"},
    )
    assert result.lifecycle is CycleState.DEBATED
    assert result.state.decision["action"] == "BUY"
    assert result.state.signals["macro"] == "BULLISH"
