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
        self.calls = []

    def build(self, rows, *, as_of, dataset="market/daily_prices"):
        rows = tuple(rows)
        self.rows.extend(rows)
        self.calls.append((rows, as_of, dataset))
        return type("Manifest", (), {"dataset": dataset, "checksum_sha256": "test"})()


def test_retry_resolves_and_publishes_recovered_rows():
    provider = Provider()
    builder = Builder()
    queue = FailureQueue([
        IngestionFailure("KRX", "000001", "2026-08-28", "2026-08-28", "RuntimeError", "temporary", 1),
        IngestionFailure("KRX", "000001", "2026-08-28", "2026-08-28", "RuntimeError", "older", 0),
    ])
    report = IngestionRetryService(
        lambda market: provider, builder, requests_per_second=1000, max_attempts=2, sleeper=lambda _: None
    ).run(queue, available_at="2026-08-28T16:00:00+00:00")
    assert report.attempted == 1
    assert report.resolved == 1
    assert report.remaining == 0
    assert provider.calls == 1
    assert len(report.rows) == 1
    assert report.dataset_manifest.dataset == "market/daily_prices"
    assert builder.calls[0][1] == "2026-08-28T16:00:00+00:00"


def test_retry_stops_at_max_attempts():
    class Broken:
        def fetch_daily_prices(self, symbol, start_date, end_date):
            raise TimeoutError("down")

    builder = Builder()
    queue = FailureQueue([
        IngestionFailure("KRX", "000002", "2026-08-28", "2026-08-28", "TimeoutError", "down", 1),
    ])
    report = IngestionRetryService(
        lambda market: Broken(), builder, max_attempts=2, sleeper=lambda _: None
    ).run(queue)
    failure = report.failures.all()[0]
    assert report.attempted == 1
    assert report.resolved == 0
    assert report.remaining == 1
    assert failure.attempts == 2
    assert failure.retryable is False
    assert builder.calls == []
