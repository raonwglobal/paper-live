from pathlib import Path

from paper_live.data_lake import GoogleDriveStorageAgent, LocalDriveMirror
from paper_live.ingestion_reconcile import RecoveryReconciler
from paper_live.ingestion_retry import IngestionRetryService
from paper_live.market_dataset import DailyDatasetBuilder, DailyPriceRecord


def row(
    symbol: str,
    trade_date: str,
    *,
    market: str = "KRX",
    source: str = "source",
    available_at: str = "2026-08-29T00:00:00+00:00",
):
    return DailyPriceRecord(
        symbol,
        market,
        trade_date,
        1,
        1,
        1,
        100,
        10,
        source=source,
        available_at=available_at,
    )


class _NoopProvider:
    def fetch_daily_prices(self, symbol, start_date, end_date):
        return ()


def test_reconciliation_adds_only_missing_recovery_keys():
    canonical = (row("A", "2026-08-28"),)
    recovery = (
        row("A", "2026-08-28", source="retry"),
        row("B", "2026-08-28", source="retry"),
    )

    merged, report = RecoveryReconciler().merge(canonical, recovery)

    assert [item.symbol for item in merged] == ["A", "B"]
    assert merged[0].source == "source"
    assert report.added_rows == 1
    assert report.duplicate_recovery_rows == 1
    assert report.output_rows == 2


def test_reconciliation_is_deterministic_for_recovery_order():
    recovery = [
        row("B", "2026-08-28", available_at="2026-08-29T02:00:00+00:00"),
        row("A", "2026-08-29", available_at="2026-08-29T01:00:00+00:00"),
    ]

    first, _ = RecoveryReconciler().merge((), recovery)
    second, _ = RecoveryReconciler().merge((), reversed(recovery))

    assert [item.as_row() for item in first] == [item.as_row() for item in second]


def test_reconciliation_preserves_canonical_duplicate_key():
    canonical = (
        row("A", "2026-08-28", source="first"),
        row("A", "2026-08-28", source="second"),
    )

    merged, report = RecoveryReconciler().merge(canonical, ())

    assert len(merged) == 1
    assert merged[0].source == "first"
    assert report.canonical_rows == 2


def test_drive_reader_loads_partitioned_rows_and_reconciliation_from_drive(tmp_path: Path):
    storage = GoogleDriveStorageAgent(LocalDriveMirror(tmp_path))
    builder = DailyDatasetBuilder(storage)
    canonical = row("A", "2026-08-28", source="canonical")
    recovery = row("B", "2026-08-28", source="retry")
    builder.build((canonical,), as_of="2026-08-29T00:00:00+00:00", dataset="market/daily_prices")
    builder.build((recovery,), as_of="2026-08-29T00:00:00+00:00", dataset="market/daily_prices/recovery")

    loaded = storage.read_partitioned_jsonl("market/daily_prices")
    assert [item["symbol"] for item in loaded] == ["A"]

    service = IngestionRetryService(lambda _: _NoopProvider(), builder)
    report, manifest = service.reconcile_from_drive(as_of="2026-08-30T00:00:00+00:00")

    assert report.added_rows == 1
    assert manifest is not None
    final_rows = storage.read_partitioned_jsonl("market/daily_prices")
    assert [item["symbol"] for item in final_rows] == ["A", "B"]


def test_daily_builder_does_not_erase_other_market_rows(tmp_path: Path):
    storage = GoogleDriveStorageAgent(LocalDriveMirror(tmp_path))
    builder = DailyDatasetBuilder(storage)
    builder.build((row("A", "2026-08-28", market="KRX"),), as_of="2026-08-29T00:00:00+00:00")
    builder.build((row("US-A", "2026-08-28", market="NASDAQ", source="toss", available_at="2026-08-29T01:00:00+00:00"),), as_of="2026-08-29T01:00:00+00:00")

    final_rows = storage.read_partitioned_jsonl("market/daily_prices")
    assert {(item["market"], item["symbol"]) for item in final_rows} == {("KRX", "A"), ("NASDAQ", "US-A")}
