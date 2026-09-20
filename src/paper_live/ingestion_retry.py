from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime

from .data_lake import DatasetManifest
from .ingestion_reconcile import ReconciliationReport, RecoveryReconciler
from .ingestion_run import FailureQueue, IngestionFailure
from .market_dataset import DailyDatasetBuilder, DailyPriceProvider, DailyPriceRecord
from .market_ingestion import ResilientDailyCollector


@dataclass(frozen=True)
class RetryReport:
    attempted: int
    resolved: int
    remaining: int
    failures: FailureQueue
    rows: tuple[DailyPriceRecord, ...] = ()
    dataset_manifest: DatasetManifest | None = None


class IngestionRetryService:
    """Bounded retry service that publishes recovered rows to an isolated recovery dataset."""

    RECOVERY_DATASET = "market/daily_prices/recovery"

    def __init__(self, provider_factory: Callable[[str], DailyPriceProvider], builder: DailyDatasetBuilder, *, requests_per_second: float = 2.0, backoff_seconds: float = 1.0, max_attempts: int = 3, sleeper=None) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self.provider_factory = provider_factory
        self.builder = builder
        self.requests_per_second = requests_per_second
        self.backoff_seconds = backoff_seconds
        self.max_attempts = max_attempts
        self.sleeper = sleeper

    @staticmethod
    def _record_from_row(row: dict[str, object]) -> DailyPriceRecord:
        required = {"symbol", "market", "trade_date", "close", "available_at"}
        if not required.issubset(row):
            missing = ", ".join(sorted(required - set(row)))
            raise ValueError(f"recovery row missing fields: {missing}")
        return DailyPriceRecord(
            symbol=str(row["symbol"]), market=str(row["market"]), trade_date=str(row["trade_date"]),
            open=float(str(row["open"])) if row.get("open") is not None else None,
            high=float(str(row["high"])) if row.get("high") is not None else None,
            low=float(str(row["low"])) if row.get("low") is not None else None,
            close=float(str(row["close"])),
            volume=float(str(row["volume"])) if row.get("volume") is not None else None,
            value=float(str(row["value"])) if row.get("value") is not None else None,
            adjusted_close=float(str(row["adjusted_close"])) if row.get("adjusted_close") is not None else None,
            source=str(row.get("source", "unknown")), currency=str(row.get("currency", "KRW")),
            available_at=str(row["available_at"]), schema_version=str(row.get("schema_version", "daily-price-v2")),
        )

    def _read_recovery_rows(self) -> tuple[DailyPriceRecord, ...]:
        storage = getattr(self.builder, "storage", None)
        if storage is None:
            return ()
        reader = getattr(storage, "read_partitioned_jsonl", None)
        if reader is None:
            return ()
        rows = reader(self.RECOVERY_DATASET)
        return tuple(self._record_from_row(dict(row)) for row in rows)

    def run(self, queue: FailureQueue, *, available_at: str | None = None) -> RetryReport:
        remaining = FailureQueue(item for item in queue.all() if not item.retryable)
        resolved = 0
        attempted = 0
        rows: list[DailyPriceRecord] = []
        available = available_at or datetime.now(UTC).isoformat()
        for failure in queue.retryable():
            if failure.attempts >= self.max_attempts:
                remaining.add(failure)
                continue
            attempted += 1
            provider = self.provider_factory(failure.market)
            collector = ResilientDailyCollector(provider, self.builder, requests_per_second=self.requests_per_second, max_retries=1, backoff_seconds=self.backoff_seconds, sleeper=self.sleeper or __import__("time").sleep)
            report = collector.collect([failure.symbol], start_date=date.fromisoformat(failure.start_date), end_date=date.fromisoformat(failure.end_date), market=failure.market, source=type(provider).__name__, available_at=available, persist=False)
            if report.complete:
                resolved += 1
                rows.extend(report.rows)
                continue
            observed = report.failures[0] if report.failures else None
            next_attempts = failure.attempts + 1
            remaining.add(IngestionFailure(market=failure.market, symbol=failure.symbol, start_date=failure.start_date, end_date=failure.end_date, error_type=type(observed).__name__ if observed else failure.error_type, error_message=observed.error if observed else failure.error_message, attempts=next_attempts, retryable=next_attempts < self.max_attempts))

        dataset_manifest = None
        if rows:
            existing = self._read_recovery_rows()
            combined = {RecoveryReconciler._key(row): row for row in existing}
            for row in rows:
                key = RecoveryReconciler._key(row)
                prior = combined.get(key)
                if prior is None or RecoveryReconciler._timestamp(row) >= RecoveryReconciler._timestamp(prior):
                    combined[key] = row
            dataset_manifest = self.builder.build(combined.values(), as_of=available, dataset=self.RECOVERY_DATASET)
        return RetryReport(attempted=attempted, resolved=resolved, remaining=len(remaining.all()), failures=remaining, rows=tuple(rows), dataset_manifest=dataset_manifest)

    def reconcile(self, canonical: Sequence[DailyPriceRecord], recovery: Iterable[DailyPriceRecord], *, as_of: str, dataset: str = "market/daily_prices", run_id: str | None = None) -> tuple[ReconciliationReport, DatasetManifest | None]:
        """Merge recovery rows and republish the complete canonical snapshot."""
        merged, report = RecoveryReconciler().merge(canonical, recovery)
        if not merged:
            return report, None
        return report, self.builder.build(merged, as_of=as_of, dataset=dataset, run_id=run_id)

    def reconcile_from_drive(self, *, as_of: str, dataset: str = "market/daily_prices", recovery_dataset: str | None = None, run_id: str | None = None) -> tuple[ReconciliationReport, DatasetManifest | None]:
        """Load canonical and recovery partitions from Drive, merge them, and republish canonical."""
        storage = getattr(self.builder, "storage", None)
        if storage is None or not hasattr(storage, "read_partitioned_jsonl"):
            raise RuntimeError("reconcile_from_drive requires a readable Drive storage agent")
        reader = storage.read_partitioned_jsonl
        canonical_rows = tuple(self._record_from_row(dict(row)) for row in reader(dataset))
        recovery_path = recovery_dataset or self.RECOVERY_DATASET
        recovery_rows = tuple(self._record_from_row(dict(row)) for row in reader(recovery_path))
        return self.reconcile(canonical_rows, recovery_rows, as_of=as_of, dataset=dataset, run_id=run_id)
