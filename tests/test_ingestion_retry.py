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


def test_retry_resolves_and_publishes_recovered_rows_to_recovery_dataset():
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
    assert report.dataset_manifest.dataset == IngestionRetryService.RECOVERY_DATASET
    assert builder.calls[0][1] == "2026-08-28T16:00:00+00:00"
    assert builder.calls[0][2] == IngestionRetryService.RECOVERY_DATASET


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


def test_retry_reconcile_republishes_merged_canonical_snapshot():
    provider = Provider()
    builder = Builder()
    service = IngestionRetryService(
        lambda market: provider, builder, max_attempts=2, sleeper=lambda _: None
    )
    from paper_live.market_dataset import DailyPriceRecord

    canonical = (
        DailyPriceRecord(
            "000001", "KRX", "2026-08-28", 1, 1, 1, 100, 10,
            source="canonical", available_at="2026-08-28T18:00:00+00:00",
        ),
    )
    recovery = (
        DailyPriceRecord(
            "000001", "KRX", "2026-08-28", 1, 1, 1, 999, 10,
            source="retry", available_at="2026-08-29T00:00:00+00:00",
        ),
        DailyPriceRecord(
            "000002", "KRX", "2026-08-28", 1, 1, 1, 101, 11,
            source="retry", available_at="2026-08-29T00:00:00+00:00",
        ),
    )

    report, manifest = service.reconcile(
        canonical,
        recovery,
        as_of="2026-08-29T01:00:00+00:00",
    )

    assert report.added_rows == 1
    assert report.duplicate_recovery_rows == 1
    assert manifest.dataset == "market/daily_prices"
    merged_rows = builder.calls[-1][0]
    assert [item.symbol for item in merged_rows] == ["000001", "000002"]
    assert merged_rows[0].close == 100
