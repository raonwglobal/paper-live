from __future__ import annotations

import math
from collections.abc import Callable
from datetime import date
from typing import Any


class YFinanceDailyPriceProvider:
    """Yahoo Finance daily OHLCV adapter; inject downloader for deterministic tests."""

    SOURCE = "yfinance"

    def __init__(self, *, market: str, downloader: Callable[..., Any] | None = None) -> None:
        self.market = market.strip().upper()
        if not self.market:
            raise ValueError("market is required")
        self._downloader = downloader

    def _download(self, ticker: str, start: date, end_exclusive: date):
        if self._downloader is not None:
            return self._downloader(ticker, start=start.isoformat(), end=end_exclusive.isoformat(),
                                    auto_adjust=False, actions=False, progress=False)
        try:
            import yfinance as yf
        except ImportError as exc:
            raise RuntimeError("install paper-live[yfinance] to use this provider") from exc
        return yf.download(ticker, start=start.isoformat(), end=end_exclusive.isoformat(),
                           auto_adjust=False, actions=False, progress=False)

    def _ticker(self, symbol: str) -> str:
        if self.market == "KOSPI" and not symbol.endswith((".KS", ".KQ")):
            return f"{symbol}.KS"
        if self.market == "KOSDAQ" and not symbol.endswith((".KS", ".KQ")):
            return f"{symbol}.KQ"
        return symbol

    def fetch_daily_prices(self, symbol: str, start_date: date, end_date: date) -> tuple[dict[str, Any], ...]:
        if start_date > end_date:
            raise ValueError("start_date cannot be after end_date")
        ticker = self._ticker(symbol.strip())
        frame = self._download(ticker, start_date, date.fromordinal(end_date.toordinal() + 1))
        if frame is None or frame.empty:
            return ()
        if getattr(frame.columns, "nlevels", 1) > 1:
            frame.columns = frame.columns.get_level_values(0)
        rows: list[dict[str, Any]] = []
        for index, record in frame.iterrows():
            trade_date = index.date().isoformat() if hasattr(index, "date") else date.fromisoformat(str(index)[:10]).isoformat()
            rows.append({
                "symbol": symbol,
                "trade_date": trade_date,
                "open": self._value(record, "Open"),
                "high": self._value(record, "High"),
                "low": self._value(record, "Low"),
                "close": self._value(record, "Close"),
                "adjusted_close": self._value(record, "Adj Close"),
                "volume": self._value(record, "Volume"),
            })
        return tuple(rows)

    @staticmethod
    def _value(record: Any, key: str) -> float | None:
        value = record.get(key)
        if value is None:
            return None
        number = float(value)
        return None if math.isnan(number) else number
