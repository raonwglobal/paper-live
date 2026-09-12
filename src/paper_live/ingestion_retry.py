from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime

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
    dataset_manifest: object | None = None


class IngestionRetryService:
    """Bounded retry service that republishes recovered rows to the canonical dataset."""

    def __init__(
        self,
        provider_factory: Callable[[str], DailyPriceProvider],
        builder: DailyDatasetBuilder,
        *,
        requests_per_second: float = 2.0,
        backoff_seconds: float = 1.0,
        max_attempts: int = 3,
        sleeper=None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self.provider_factory = provider_factory
        self.builder = builder
        self.requests_per_second = requests_per_second
        self.backoff_seconds = backoff_seconds
        self.max_attempts = max_attempts
        self.sleeper = sleeper

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
            collector = ResilientDailyCollector(
                provider,
                self.builder,
                requests_per_second=self.requests_per_second,
                max_retries=1,
                backoff_seconds=self.backoff_seconds,
                sleeper=self.sleeper or __import__("time").sleep,
            )
            report = collector.collect(
                [failure.symbol],
                start_date=date.fromisoformat(failure.start_date),
                end_date=date.fromisoformat(failure.end_date),
                market=failure.market,
                source=type(provider).__name__,
                available_at=available,
                persist=False,
            )
            if report.symbols_ok:
                resolved += 1
                rows.extend(report.rows)
                continue
            observed = report.failures[0] if report.failures else None
            next_failure = IngestionFailure(
                market=failure.market,
                symbol=failure.symbol,
                start_date=failure.start_date,
                end_date=failure.end_date,
                error_type=type(observed).__name__ if observed else failure.error_type,
                error_message=observed.error if observed else failure.error_message,
                attempts=failure.attempts + 1,
                retryable=failure.attempts + 1 < self.max_attempts,
            )
            remaining.add(next_failure)
        dataset_manifest = self.builder.build(rows, as_of=available) if rows else None
        return RetryReport(
            attempted=attempted,
            resolved=resolved,
            remaining=len(remaining.all()),
            failures=remaining,
            rows=tuple(rows),
            dataset_manifest=dataset_manifest,
        )
