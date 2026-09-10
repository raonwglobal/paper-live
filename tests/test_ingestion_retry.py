from datetime import date

from paper_live.ingestion_retry import IngestionRetryService
from paper_live.ingestion_run import FailureQueue, IngestionFailure


class Provider:
    def __init__(self):
        self.calls = 0

    def fetch_daily_prices(self, symbol, start_date, end_date):
        self.calls += 1
        return [{"symbol": symbol, "date": start_date.isoformat(), "close": "101", "volume": "11"}]


class Builder:
    def __init__(self):
        self.rows = []

    def build(self, rows, *, as_of, dataset="market/daily_prices"):
        self.rows.extend(rows)
        return type("Manifest", (), {"dataset": dataset, "checksum_sha256": "test"})()


def test_retry_resolves_retryable_failure_and_deduplicates():
    provider = Provider()
    queue = FailureQueue([
        IngestionFailure("KRX", "000001", "2026-08-28", "2026-08-28", "RuntimeError", "temporary", 3),
        IngestionFailure("KRX", "000001", "2026-08-28", "2026-08-28", "RuntimeError", "older", 2),
    ])
    report = IngestionRetryService(lambda market: provider, Builder(), requests_per_second=1000, sleeper=lambda _: None).run(queue)
    assert report.attempted == 1
    assert report.resolved == 1
    assert report.remaining == 0
    assert provider.calls == 1
