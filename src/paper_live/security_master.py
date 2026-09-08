from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class Security:
    symbol: str
    name: str
    market: str
    country: str
    currency: str
    asset_class: str = "EQUITY"
    active: bool = True
    exchange: str | None = None


class SecurityMaster:
    """Canonical instrument registry used by ingestion, screening and execution."""

    def __init__(self, securities: Sequence[Security] | None = None):
        self._items: dict[tuple[str, str], Security] = {}
        self.replace(securities or ())

    def replace(self, securities: Iterable[Security]) -> None:
        items = {}
        for s in securities:
            symbol = s.symbol.strip()
            if not symbol or not s.name.strip() or not s.market.strip():
                raise ValueError("symbol, name and market are required")
            key = (s.market.upper(), symbol.upper())
            if key in items:
                raise ValueError(f"duplicate security: {key}")
            items[key] = Security(
                symbol=symbol,
                name=s.name.strip(),
                market=s.market.upper(),
                country=s.country.upper(),
                currency=s.currency.upper(),
                asset_class=s.asset_class.upper(),
                active=s.active,
                exchange=s.exchange,
            )
        self._items = items

    def all_active(self, market: str | None = None) -> tuple[Security, ...]:
        values = [s for s in self._items.values() if s.active and (market is None or s.market == market.upper())]
        return tuple(sorted(values, key=lambda s: (s.market, s.symbol)))

    def symbols(self, market: str | None = None) -> tuple[str, ...]:
        return tuple(s.symbol for s in self.all_active(market))

    def get(self, market: str, symbol: str) -> Security | None:
        return self._items.get((market.upper(), symbol.upper()))

    def as_of(self) -> str:
        return datetime.now(UTC).isoformat()


def batch_symbols(master: SecurityMaster, *, market: str | None = None, batch_size: int = 200) -> list[tuple[str, ...]]:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    symbols = master.symbols(market)
    return [symbols[i : i + batch_size] for i in range(0, len(symbols), batch_size)]
