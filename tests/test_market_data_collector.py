from datetime import date

import pytest

from paper_live.market_data_collector import DailyMarketDataCollector
from paper_live.universe import Security, SecurityMaster


class Provider:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def fetch_daily_prices(self, symbol, start_date, end_date):
        self.calls.append((symbol, start_date, end_date))
        if isinstance(self.rows, Exception):
            raise self.rows
        return self.rows


class Storage:
    def __init__(self):
        self.calls = []

    def write_partitioned_jsonl(self, dataset, partitions, **kwargs):
        self.calls.append((dataset, dict(partitions), kwargs))
        return {"row_count": sum(map(len, partitions.values())), **kwargs}


def test_collect_enriches_rows_and_uses_one_provider_per_market():
    day = date(2026, 9, 30)
    provider = Provider(({"symbol": "005930", "trade_date": "2026-09-30", "close": 70000},))
    storage = Storage()
    collector = DailyMarketDataCollector(
        SecurityMaster([Security("005930", "Samsung", "KOSPI")]),
        lambda market: provider,
        storage,
    )

    report = collector.collect(day, day, run_id="run-1")

    assert report.requested == report.succeeded == 1
    assert report.failed == 0
    assert report.quality.passed
    assert report.quality.row_count == 1
    dataset, partitions, metadata = storage.calls[0]
    assert dataset == "market/daily-prices"
    assert partitions["2026-09-30"][0]["name"] == "Samsung"
    assert partitions["2026-09-30"][0]["market"] == "KOSPI"
    assert partitions["2026-09-30"][0]["effective_date"] == "2026-09-30"
    assert partitions["2026-09-30"][0]["available_at"] == "2026-09-30T23:59:59+00:00"
    assert metadata["run_id"] == "run-1"


def test_collect_records_symbol_failure_and_continues():
    day = date(2026, 9, 30)
    providers = {
        "KOSPI": Provider(RuntimeError("network unavailable")),
        "NASDAQ": Provider(({"trade_date": "2026-09-30", "close": 12.0},)),
    }
    storage = Storage()
    collector = DailyMarketDataCollector(
        SecurityMaster([
            Security("005930", "Samsung", "KOSPI"),
            Security("ABC", "Example", "NASDAQ", "USD"),
        ]),
        lambda market: providers[market],
        storage,
    )

    report = collector.collect(day, day)

    assert report.succeeded == 1
    assert report.failed == 1
    assert report.failures == (("KOSPI", "005930", "RuntimeError"),)
    assert storage.calls[0][2]["failure_count"] == 1


@pytest.mark.parametrize(
    "row",
    [
        {"trade_date": "2026-10-01", "close": 1},
        {"trade_date": "2026-09-30", "close": -1},
        {"trade_date": "2026-09-30", "close": float("nan")},
        {"trade_date": "2026-09-30", "close": float("inf")},
        {"trade_date": "2026-09-30", "close": True},
    ],
)
def test_invalid_provider_rows_fail_closed(row):
    day = date(2026, 9, 30)
    collector = DailyMarketDataCollector(
        SecurityMaster([Security("X", "Example", "US", "USD")]),
        lambda _: Provider((row,)),
        Storage(),
    )

    report = collector.collect(day, day)

    assert report.failed == 1
    assert report.succeeded == 0


def test_rejects_reversed_date_range():
    collector = DailyMarketDataCollector(SecurityMaster(), lambda _: Provider(()), Storage())
    with pytest.raises(ValueError, match="end_date"):
        collector.collect(date(2026, 10, 2), date(2026, 10, 1))



def test_collect_reports_duplicate_rows_in_quality_metrics():
    day = date(2026, 9, 30)
    duplicate = {"symbol": "X", "trade_date": "2026-09-30", "close": 10}
    collector = DailyMarketDataCollector(
        SecurityMaster([Security("X", "Example", "US", "USD")]),
        lambda _: Provider((duplicate, duplicate)),
        Storage(),
    )

    report = collector.collect(day, day)

    assert report.quality.row_count == 2
    assert report.quality.duplicate_count == 1
    assert not report.quality.passed
