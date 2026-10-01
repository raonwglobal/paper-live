from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from paper_live.yfinance_provider import YFinanceDailyPriceProvider


class FakeFrame:
    empty = False
    columns = SimpleNamespace(nlevels=1)

    def iterrows(self):
        return iter([
            (date(2026, 9, 30), {
                "Open": 100.0,
                "High": 110.0,
                "Low": 90.0,
                "Close": 105.0,
                "Adj Close": 104.0,
                "Volume": 1234,
            })
        ])


def test_korean_ticker_and_inclusive_end_date():
    calls = []

    def download(ticker, **kwargs):
        calls.append((ticker, kwargs))
        return FakeFrame()

    provider = YFinanceDailyPriceProvider(market="KOSPI", downloader=download)
    rows = provider.fetch_daily_prices("005930", date(2026, 9, 1), date(2026, 9, 30))

    assert calls[0][0] == "005930.KS"
    assert calls[0][1]["end"] == "2026-10-01"
    assert rows[0]["trade_date"] == "2026-09-30"
    assert rows[0]["adjusted_close"] == 104.0
    assert rows[0]["volume"] == 1234


def test_kosdaq_suffix_and_existing_suffix_preserved():
    provider = YFinanceDailyPriceProvider(market="KOSDAQ")
    assert provider._ticker("035720") == "035720.KQ"
    assert provider._ticker("035720.KS") == "035720.KS"


def test_invalid_date_range_rejected():
    provider = YFinanceDailyPriceProvider(market="NYSE", downloader=lambda *_a, **_k: None)
    with pytest.raises(ValueError, match="start_date cannot be after end_date"):
        provider.fetch_daily_prices("AAPL", date(2026, 10, 2), date(2026, 10, 1))


def test_empty_frame_returns_no_rows():
    class EmptyFrame:
        empty = True

    provider = YFinanceDailyPriceProvider(market="NYSE", downloader=lambda *_a, **_k: EmptyFrame())
    assert provider.fetch_daily_prices("AAPL", date(2026, 9, 1), date(2026, 9, 30)) == ()
