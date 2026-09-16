from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from typing import Any, Protocol

from .data_lake import DatasetManifest, GoogleDriveStorageAgent


class DailyPriceProvider(Protocol):
    def fetch_daily_prices(self, symbol: str, start_date: date, end_date: date) -> Sequence[Mapping[str, Any]]: ...


@dataclass(frozen=True)
class DailyPriceRecord:
    symbol: str
    market: str
    trade_date: str
    open: float | None
    high: float | None
    low: float | None
    close: float
    volume: float | None
    value: float | None = None
    adjusted_close: float | None = None
    source: str = "unknown"
    currency: str = "KRW"
    available_at: str = ""
    schema_version: str = "daily-price-v2"

    def as_row(self) -> dict[str, Any]:
        return asdict(self)


class DailyPriceNormalizer:
    FIELD_ALIASES = {
        "symbol": ("symbol", "code", "ticker", "isu_cd"),
        "trade_date": ("trade_date", "date", "stck_bsop_date", "trading_date"),
        "open": ("open", "open_price", "stck_oprc"),
        "high": ("high", "high_price", "stck_hgpr"),
        "low": ("low", "low_price", "stck_lwpr"),
        "close": ("close", "close_price", "stck_clpr"),
        "volume": ("volume", "trade_volume", "acml_vol"),
        "value": ("value", "trade_value", "acml_tr_pbmn"),
        "adjusted_close": ("adjusted_close", "adj_close"),
    }

    @classmethod
    def _get(cls, row: Mapping[str, Any], field: str, default: Any = None) -> Any:
        for key in cls.FIELD_ALIASES[field]:
            if key in row and row[key] not in (None, ""):
                return row[key]
        return default

    @staticmethod
    def _number(value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _date(value: Any) -> str:
        raw = str(value or "").strip().replace("/", "-")
        if len(raw) == 8 and raw.isdigit():
            return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
        return date.fromisoformat(raw).isoformat()

    @classmethod
    def normalize(
        cls, row: Mapping[str, Any], *, symbol: str, market: str, source: str, available_at: str
    ) -> DailyPriceRecord:
        code = str(cls._get(row, "symbol", symbol) or symbol).strip()
        normalized_market = str(market).strip().upper()
        normalized_source = str(source).strip() or "unknown"
        if not normalized_market:
            raise ValueError("daily price requires market")
        trade_date = cls._date(cls._get(row, "trade_date"))
        close = cls._number(cls._get(row, "close"))
        if not code or close is None:
            raise ValueError("daily price requires symbol and close")
        return DailyPriceRecord(
            symbol=code,
            market=normalized_market,
            trade_date=trade_date,
            open=cls._number(cls._get(row, "open")),
            high=cls._number(cls._get(row, "high")),
            low=cls._number(cls._get(row, "low")),
            close=close,
            volume=cls._number(cls._get(row, "volume")),
            value=cls._number(cls._get(row, "value")),
            adjusted_close=cls._number(cls._get(row, "adjusted_close")),
            source=normalized_source,
            available_at=available_at,
        )


class DailyDatasetBuilder:
    def __init__(self, storage: GoogleDriveStorageAgent):
        self.storage = storage

    def build(
        self, rows: Iterable[DailyPriceRecord], *, as_of: str, dataset: str = "market/daily_prices", run_id: str | None = None
    ) -> DatasetManifest:
        unique: dict[tuple[str, str, str], DailyPriceRecord] = {}
        for row in rows:
            if not row.available_at:
                raise ValueError("daily price row requires available_at")
            try:
                available = datetime.fromisoformat(row.available_at.replace("Z", "+00:00"))
                effective = date.fromisoformat(row.trade_date)
            except ValueError as exc:
                raise ValueError("invalid trade_date or available_at") from exc
            if available.date() < effective:
                raise ValueError("available_at cannot precede trade_date")
            unique[(row.market, row.symbol, row.trade_date)] = row
        ordered = sorted(unique.values(), key=lambda r: (r.market, r.symbol, r.trade_date))
        partitions: dict[str, list[dict[str, Any]]] = {}
        for row in ordered:
            partitions.setdefault(row.trade_date, []).append(row.as_row())
        return self.storage.write_partitioned_jsonl(
            dataset,
            partitions,
            as_of=as_of,
            schema_version="daily-price-v2",
            run_id=run_id,
            source=ordered[0].source if ordered else None,
        )


class DailyPriceIngestionService:
    def __init__(self, provider: DailyPriceProvider, builder: DailyDatasetBuilder):
        self.provider = provider
        self.builder = builder

    def collect(
        self,
        symbols: Sequence[str],
        *,
        start_date: date,
        end_date: date,
        market: str,
        source: str,
        available_at: str | None = None,
        run_id: str | None = None,
    ) -> DatasetManifest:
        if start_date > end_date:
            raise ValueError("start_date cannot be after end_date")
        available = available_at or datetime.now(UTC).isoformat()
        rows: list[DailyPriceRecord] = []
        for symbol in sorted(set(s.strip() for s in symbols if s.strip())):
            payload = self.provider.fetch_daily_prices(symbol, start_date, end_date)
            for item in payload:
                rows.append(
                    DailyPriceNormalizer.normalize(
                        item, symbol=symbol, market=market, source=source, available_at=available
                    )
                )
        return self.builder.build(rows, as_of=available, run_id=run_id)
