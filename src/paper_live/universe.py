from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class Security:
    symbol: str
    name: str
    market: str
    currency: str = "KRW"
    active: bool = True


class SecurityMaster:
    """Deterministic, versionable security universe used by batch collectors."""

    def __init__(self, securities: Iterable[Security] = ()):
        self._items: dict[tuple[str, str], Security] = {}
        self.replace(securities)

    def replace(self, securities: Iterable[Security]) -> None:
        items = {}
        for security in securities:
            if not security.symbol or not security.market:
                raise ValueError("symbol and market are required")
            key = (security.market, security.symbol)
            if key in items:
                raise ValueError(f"duplicate security: {key}")
            items[key] = security
        self._items = items

    def active(self, market: str | None = None) -> tuple[Security, ...]:
        values = [x for x in self._items.values() if x.active and (market is None or x.market == market)]
        return tuple(sorted(values, key=lambda x: (x.market, x.symbol)))

    def symbols(self, market: str | None = None) -> tuple[str, ...]:
        return tuple(x.symbol for x in self.active(market))

    def batch(self, size: int = 200, market: str | None = None) -> tuple[tuple[Security, ...], ...]:
        if size < 1:
            raise ValueError("size must be positive")
        values = self.active(market)
        return tuple(tuple(values[i : i + size]) for i in range(0, len(values), size))
