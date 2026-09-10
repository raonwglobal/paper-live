from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable

from .ingestion_run import FailureQueue, IngestionFailure
from .market_dataset import DailyDatasetBuilder, DailyPriceProvider
from .market_ingestion import ResilientDailyCollector


@dataclass(frozen=True)
class RetryReport:
    attempted: int
    resolved: int
    remaining: int
    failures: FailureQueue


class IngestionRetryService:
    """Deterministically retries only retryable ingestion failures.

    Retry execution is data-only and never creates broker orders.
    """

    def __init__(self, provider_factory: Callable[[str], DailyPriceProvider], builder: DailyDatasetBuilder,
                 *, requests_per_second: float = 2.0, backoff_seconds: float = 1.0, sleeper=None) -> None:
        self.provider_factory = provider_factory
        self.builder = builder
        self.requests_per_second = requests_per_second
        self.backoff_seconds = backoff_seconds
        self.sleeper = sleeper

    def run(self, queue: FailureQueue, *, available_at: str | None = None) -> RetryReport:
        remaining = FailureQueue(item for item in queue.all() if not item.retryable)
        resolved = 0
        attempted = 0
        for failure in queue.retryable():
            attempted += 1
            provider = self.provider_factory(failure.market)
            collector = ResilientDailyCollector(
                provider, self.builder, requests_per_second=self.requests_per_second,
                max_retries=1, backoff_seconds=self.backoff_seconds,
                sleeper=self.sleeper or __import__("time").sleep,
            )
            report = collector.collect(
                [failure.symbol], start_date=date.fromisoformat(failure.start_date),
                end_date=date.fromisoformat(failure.end_date), market=failure.market,
                source=type(provider).__name__, available_at=available_at or failure.end_date,
            )
            if report.symbols_ok:
                resolved += 1
                continue
            observed = report.failures[0] if report.failures else None
            remaining.add(IngestionFailure(
                market=failure.market, symbol=failure.symbol,
                start_date=failure.start_date, end_date=failure.end_date,
                error_type=type(observed).__name__ if observed else failure.error_type,
                error_message=observed.error if observed else failure.error_message,
                attempts=failure.attempts + 1,
                retryable=True,
            ))
        return RetryReport(attempted, resolved, len(remaining.all()), remaining)
