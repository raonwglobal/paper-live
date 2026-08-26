from decimal import Decimal
from pathlib import Path

from paper_live.analytics import OHLCV, max_drawdown, rsi, screen, ScreenRule, sharpe_ratio
from paper_live.backtest import BacktestRunner
from paper_live.environment import EnvironmentController
from paper_live.execution import ExecutionGateway, OrderRequest, OrderSide, PaperAccount, VirtualMatchingEngine
from paper_live.reflection import EpisodicMemory, SelfReflectionWorker, TradeEpisode


def candles():
    return [OHLCV(str(i), Decimal("10"), Decimal("11"), Decimal("9"), Decimal(str(10 + i)), Decimal("1000")) for i in range(20)]


def test_rsi_and_screener():
    cs = candles()
    values = rsi([x.close for x in cs])
    assert values[-1] is not None
    assert screen(cs, ScreenRule(min_volume=Decimal("500"))) == cs


def test_metrics():
    assert sharpe_ratio([Decimal("0.01"), Decimal("0.02")]) > 0
    assert max_drawdown([Decimal("100"), Decimal("110"), Decimal("99")]) < 0


def test_backtest_runner():
    account = PaperAccount(Decimal("100000"))
    gateway = ExecutionGateway(EnvironmentController(), VirtualMatchingEngine(account))
    def strategy(i, history):
        if i == 0:
            return OrderRequest("ABC", OrderSide.BUY, Decimal("1"))
        if i == len(history) - 1 and i == 5:
            return OrderRequest("ABC", OrderSide.SELL, Decimal("1"))
        return None
    result = BacktestRunner(gateway, account).run(candles()[:6], strategy)
    assert result.fills == 2
    assert result.final_cash > 0


def test_reflection(tmp_path: Path):
    memory = EpisodicMemory(tmp_path / "episodes.jsonl")
    worker = SelfReflectionWorker(memory)
    episode = TradeEpisode("1", "ABC", "BUY", "10", "11", "1", {"signal": "BUY"}, "WIN", "2026-08-26T00:00:00Z")
    result = worker.reflect(episode)
    assert result["verdict"] == "POSITIVE"
    assert len(memory.read_all()) == 1
