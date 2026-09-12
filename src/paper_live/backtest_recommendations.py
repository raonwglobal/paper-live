from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from .analytics import OHLCV
from .backtest import BacktestResult, BacktestRunner
from .execution import OrderSide, OrderType, PaperOrderRequest


class RecommendationBacktest:
    """Point-in-time replay: today's recommendation may only trade on a later candle."""

    def __init__(self, runner: BacktestRunner):
        self.runner = runner

    def run(
        self, candles: Sequence[OHLCV], recommendations: Sequence[dict[str, Any]], *, quantity: Decimal = Decimal("1")
    ) -> BacktestResult:
        by_date = {str(r.get("trade_date") or r.get("decision_date")): r for r in recommendations}

        def strategy(i: int, history: Sequence[OHLCV]) -> PaperOrderRequest | None:
            if i == 0:
                return None
            current = candles[i]
            previous = candles[i - 1]
            rec = by_date.get(str(getattr(previous, "timestamp", ""))[:10])
            if not rec or str(rec.get("decision_time", "")) >= str(getattr(current, "timestamp", "")):
                return None
            symbol = str(rec.get("symbol", ""))
            if not symbol:
                return None
            if float(rec.get("score", 0)) <= 0:
                return None
            return PaperOrderRequest(symbol, OrderSide.BUY, quantity, OrderType.MARKET, None, "")

        return self.runner.run(candles, strategy)
