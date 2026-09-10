from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Callable

from .market_dataset import DailyDatasetBuilder, DailyPriceProvider, DailyPriceRecord
from .market_ingestion import IngestionFailure as CollectorFailure, IngestionReport, ResilientDailyCollector
from .universe import SecurityMaster


@dataclass(frozen=True)
class MarketIngestionJobReport:
    started_at: str
    completed_at: str
    markets: tuple[str, ...]
    records: int
    symbols_ok: int
    failures: int
    failure_details: tuple[tuple[str, CollectorFailure], ...] = ()
    dataset_manifest: object | None = None


class MarketIngestionJob:
    """Runs deterministic universe batches and publishes one canonical dataset."""

    def __init__(self, universe: SecurityMaster, provider_factory: Callable[[str], DailyPriceProvider],
                 builder: DailyDatasetBuilder, *, batch_size: int = 200,
                 requests_per_second: float = 2.0, max_retries: int = 3,
                 backoff_seconds: float = 1.0, sleeper=None):
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        self.universe = universe
        self.provider_factory = provider_factory
        self.builder = builder
        self.batch_size = batch_size
        self.requests_per_second = requests_per_second
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.sleeper = sleeper

    def run(self, *, start_date: date, end_date: date, available_at: str | None = None) -> MarketIngestionJobReport:
        started = datetime.now(UTC)
        available = available_at or started.isoformat()
        total_ok = total_failures = 0
        details: list[tuple[str, CollectorFailure]] = []
        rows: list[DailyPriceRecord] = []
        markets = sorted({s.market for s in self.universe.active()})
        for market in markets:
            provider = self.provider_factory(market)
            collector = ResilientDailyCollector(
                provider, self.builder, requests_per_second=self.requests_per_second,
                max_retries=self.max_retries, backoff_seconds=self.backoff_seconds,
                sleeper=self.sleeper or __import__("time").sleep,
            )
            for batch in self.universe.batch(self.batch_size, market):
                report: IngestionReport = collector.collect(
                    [s.symbol for s in batch], start_date=start_date, end_date=end_date,
                    market=market, source=type(provider).__name__, available_at=available, persist=False,
                )
                rows.extend(report.rows)
                total_ok += report.symbols_ok
                total_failures += len(report.failures)
                details.extend((market, failure) for failure in report.failures)
        dataset_manifest = self.builder.build(rows, as_of=available) if rows else None
        return MarketIngestionJobReport(started.isoformat(), datetime.now(UTC).isoformat(), tuple(markets),
                                        len(rows), total_ok, total_failures, tuple(details), dataset_manifest)
