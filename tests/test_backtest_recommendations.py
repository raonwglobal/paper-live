from decimal import Decimal

from paper_live.analytics import OHLCV
from paper_live.backtest import BacktestRunner
from paper_live.backtest_recommendations import RecommendationBacktest
from paper_live.environment import EnvironmentController
from paper_live.execution import ExecutionGateway, PaperAccount, VirtualMatchingEngine


def test_recommendation_replay_uses_later_candle():
    candles = [
        OHLCV(
            "2026-08-28T18:00:00+09:00",
            Decimal("100"),
            Decimal("100"),
            Decimal("100"),
            Decimal("100"),
            Decimal("1000"),
        ),
        OHLCV(
            "2026-08-29T18:00:00+09:00",
            Decimal("110"),
            Decimal("110"),
            Decimal("110"),
            Decimal("110"),
            Decimal("1000"),
        ),
    ]
    # decision on day 1 is consumed on day 2, never on the same candle.
    rec = [{"symbol": "A", "trade_date": "2026-08-28", "decision_time": "2026-08-28T19:00:00+09:00", "score": 80}]
    account = PaperAccount(Decimal("1000"))
    controller = EnvironmentController()
    gateway = ExecutionGateway(controller, VirtualMatchingEngine(account, slippage_bps=Decimal("0")))
    runner = BacktestRunner(gateway, account)
    result = RecommendationBacktest(runner).run(candles, rec, quantity=Decimal("1"))
    assert result.fills == 1
