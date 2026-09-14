from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal


@dataclass(frozen=True)
class ReflectionRecord:
    plugin_id: str
    skill_id: str
    symbol: str
    pnl: Decimal
    outcome: str
    timestamp: str


class EpisodicMemory:
    def __init__(self):
        self._records: list[ReflectionRecord] = []

    def record(self, plugin_id: str, skill_id: str, symbol: str, pnl: Decimal, outcome: str) -> ReflectionRecord:
        record = ReflectionRecord(plugin_id, skill_id, symbol, pnl, outcome, datetime.now(UTC).isoformat())
        self._records.append(record)
        return record

    def query(self, plugin_id: str | None = None) -> tuple[ReflectionRecord, ...]:
        if plugin_id is None:
            return tuple(self._records)
        return tuple(r for r in self._records if r.plugin_id == plugin_id)
