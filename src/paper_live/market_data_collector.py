from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

from .data_lake import DatasetManifest, GoogleDriveStorageAgent
from .universe import Security, SecurityMaster


class DailyPriceProvider(Protocol):
    def fetch_daily_prices(self, symbol: str, start_date: date, end_date: date) -> tuple[dict[str, Any], ...]: ...


@dataclass(frozen=True)
class CollectionReport:
    manifest: DatasetManifest
    requested: int
    succeeded: int
    failed: int
    failures: tuple[tuple[str, str, str], ...]


class DailyMarketDataCollector:
    """Collect a security universe and persist validated date partitions."""

    def __init__(
        self,
        universe: SecurityMaster,
        provider_factory: Callable[[str], DailyPriceProvider],
        storage: GoogleDriveStorageAgent,
        *,
        dataset: str = "market/daily-prices",
    ) -> None:
        self.universe = universe
        self.provider_factory = provider_factory
        self.storage = storage
        self.dataset = dataset.strip("/")
        if not self.dataset:
            raise ValueError("dataset is required")

    def collect(
        self,
        start_date: date,
        end_date: date,
        *,
        as_of: str | None = None,
        run_id: str | None = None,
    ) -> CollectionReport:
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")
        securities = self.universe.active()
        partitions: dict[str, list[dict[str, Any]]] = defaultdict(list)
        failures: list[tuple[str, str, str]] = []
        succeeded = 0
        providers: dict[str, DailyPriceProvider] = {}
        for security in securities:
            try:
                if security.market not in providers:
                    providers[security.market] = self.provider_factory(security.market)
                provider = providers[security.market]
                rows = provider.fetch_daily_prices(security.symbol, start_date, end_date)
                for raw in rows:
                    row = self._normalize(raw, security, start_date, end_date)
                    partitions[row["trade_date"]].append(row)
                succeeded += 1
            except Exception as exc:
                failures.append((security.market, security.symbol, type(exc).__name__))
        effective_as_of = as_of or end_date.isoformat()
        manifest = self.storage.write_partitioned_jsonl(
            self.dataset,
            partitions,
            as_of=effective_as_of,
            run_id=run_id,
            success_count=succeeded,
            failure_count=len(failures),
            source="paper-live-daily-collector",
        )
        return CollectionReport(manifest, len(securities), succeeded, len(failures), tuple(failures))

    @staticmethod
    def _normalize(
        raw: Mapping[str, Any],
        security: Security,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        trade_date = date.fromisoformat(str(raw.get("trade_date", "")))
        if not start_date <= trade_date <= end_date:
            raise ValueError("provider returned a row outside requested date range")
        if str(raw.get("symbol", security.symbol)) != security.symbol:
            raise ValueError("provider returned a mismatched symbol")
        row = dict(raw)
        row.update(
            symbol=security.symbol,
            name=security.name,
            market=security.market,
            currency=security.currency,
            trade_date=trade_date.isoformat(),
            source=str(raw.get("source") or "yfinance"),
        )
        for field in ("open", "high", "low", "close", "adjusted_close", "volume"):
            value = row.get(field)
            if value is not None and (not isinstance(value, (int, float)) or value < 0):
                raise ValueError(f"invalid {field} value")
        return row
