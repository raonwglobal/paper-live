from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from time import sleep

from .market_dataset import DailyDatasetBuilder, DailyPriceNormalizer, DailyPriceProvider, DailyPriceRecord


@dataclass(frozen=True)
class IngestionFailure:
    symbol: str
    error: str
    attempts: int


@dataclass(frozen=True)
class IngestionReport:
    records: int
    symbols_ok: int
    failures: tuple[IngestionFailure, ...]
    manifest: object | None


class RateLimiter:
    def __init__(self, requests_per_second: float = 2.0, sleeper: Callable[[float], None] = sleep):
        if requests_per_second <= 0:
            raise ValueError("requests_per_second must be positive")
        self.delay, self.sleeper, self._first = 1.0 / requests_per_second, sleeper, True

    def wait(self) -> None:
        if not self._first:
            self.sleeper(self.delay)
        self._first = False


class ResilientDailyCollector:
    def __init__(
        self,
        provider: DailyPriceProvider,
        builder: DailyDatasetBuilder,
        *,
        requests_per_second: float = 2.0,
        max_retries: int = 3,
        backoff_seconds: float = 1.0,
        sleeper: Callable[[float], None] = sleep,
    ):
        if max_retries < 1:
            raise ValueError("max_retries must be >= 1")
        self.provider, self.builder = provider, builder
        self.limiter, self.max_retries, self.backoff_seconds, self.sleeper = (
            RateLimiter(requests_per_second, sleeper),
            max_retries,
            backoff_seconds,
            sleeper,
        )

    def collect(
        self, symbols: Sequence[str], *, start_date: date, end_date: date, market: str, source: str, available_at: str
    ) -> IngestionReport:
        rows: list[DailyPriceRecord] = []
        failures: list[IngestionFailure] = []
        ok = 0
        for symbol in sorted(set(s.strip() for s in symbols if s.strip())):
            last_error = ""
            for attempt in range(1, self.max_retries + 1):
                try:
                    self.limiter.wait()
                    payload = self.provider.fetch_daily_prices(symbol, start_date, end_date)
                    rows.extend(
                        DailyPriceNormalizer.normalize(
                            item, symbol=symbol, market=market, source=source, available_at=available_at
                        )
                        for item in payload
                    )
                    ok += 1
                    break
                except Exception as exc:
                    last_error = type(exc).__name__
                    if attempt < self.max_retries:
                        self.sleeper(self.backoff_seconds * (2 ** (attempt - 1)))
            else:
                failures.append(IngestionFailure(symbol, last_error, self.max_retries))
        manifest = self.builder.build(rows, as_of=available_at) if rows else None
        return IngestionReport(len(rows), ok, tuple(failures), manifest)
