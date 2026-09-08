from decimal import Decimal
from paper_live.backtest_recommendations import RecommendationBacktest
from paper_live.analytics import OHLCV
from paper_live.backtest import BacktestRunner
from paper_live.execution import PaperAccount, VirtualExecutionGateway

def test_recommendation_replay_uses_later_candle():
    candles=[
      OHLCV("A","2026-08-28T18:00:00+09:00",Decimal("100"),Decimal("100"),Decimal("100"),Decimal("100"),Decimal("1000")),
      OHLCV("A","2026-08-29T18:00:00+09:00",Decimal("110"),Decimal("110"),Decimal("110"),Decimal("110"),Decimal("1000")),
    ]
    # decision on day 1 is consumed on day 2, never on the same candle.
    rec=[{"symbol":"A","trade_date":"2026-08-28","decision_time":"2026-08-28T19:00:00+09:00","score":80}]
    runner=BacktestRunner(VirtualExecutionGateway(), PaperAccount(Decimal("1000")))
    result=RecommendationBacktest(runner).run(candles,rec,quantity=Decimal("1"))
    assert result.fills == 1
