from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, TypeVar


class RowLike(Protocol):
    market: str
    symbol: str
    trade_date: str
    available_at: str


T = TypeVar("T", bound=RowLike)


@dataclass(frozen=True)
class ReconciliationReport:
    canonical_rows: int
    recovery_rows: int
    added_rows: int
    replaced_rows: int
    duplicate_recovery_rows: int
    output_rows: int


class RecoveryReconciler:
    """Merge recovered observations into a canonical snapshot deterministically.

    Canonical rows win on an identical (market, symbol, trade_date) key. Recovery
    rows only fill missing keys, preventing a partial retry from replacing an
    already-published observation.
    """

    @staticmethod
    def _key(row: RowLike) -> tuple[str, str, str]:
        return (row.market.strip().upper(), row.symbol.strip(), row.trade_date)

    @staticmethod
    def _timestamp(row: RowLike) -> datetime:
        return datetime.fromisoformat(row.available_at.replace("Z", "+00:00"))

    def merge(self, canonical: Sequence[T], recovery: Iterable[T]) -> tuple[tuple[T, ...], ReconciliationReport]:
        merged: dict[tuple[str, str, str], T] = {}
        for row in canonical:
            key = self._key(row)
            if key in merged:
                # Canonical snapshots are expected to be unique; preserve the
                # first deterministic occurrence rather than silently replacing it.
                continue
            merged[key] = row

        recovery_rows = tuple(recovery)
        added = 0
        replaced = 0
        duplicates = 0
        for row in sorted(recovery_rows, key=lambda item: (self._key(item), self._timestamp(item))):
            key = self._key(row)
            if key in merged:
                duplicates += 1
                continue
            merged[key] = row
            added += 1

        ordered = tuple(sorted(merged.values(), key=lambda row: self._key(row)))
        return ordered, ReconciliationReport(
            canonical_rows=len(canonical),
            recovery_rows=len(recovery_rows),
            added_rows=added,
            replaced_rows=replaced,
            duplicate_recovery_rows=duplicates,
            output_rows=len(ordered),
        )
