from decimal import Decimal
from paper_live import EnvironmentController, ExecutionGateway, PaperAccount, VirtualMatchingEngine
from paper_live.pipeline import TradingPipeline
from paper_live.risk import RiskGuardian
from paper_live.reflection import EpisodicMemory
from paper_live.state_machine import CycleState

def test_pipeline_executes_and_reflects(tmp_path):
    account = PaperAccount(Decimal("100000"))
    controller = EnvironmentController()
    gateway = ExecutionGateway(controller, VirtualMatchingEngine(account))
    risk = RiskGuardian(controller, account)
    memory = EpisodicMemory(str(tmp_path / "memory.jsonl"))
    result = TradingPipeline(gateway, risk, memory).run("ABC", {"macro_regime":"BULLISH", "fundamental_signal":"BUY", "technical_signal":"BUY", "sentiment_signal":"POSITIVE"}, Decimal("10"), Decimal("100"))
    assert result.action == "BUY"
    assert result.executed
    assert result.lifecycle is CycleState.REFLECTED
    assert memory.recent(1)[0]["symbol"] == "ABC"
