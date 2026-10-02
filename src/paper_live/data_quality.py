from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class DataQualityReport:
    row_count: int
    duplicate_count: int
    invalid_count: int
    missing_close_count: int
    date_out_of_range_count: int

    @property
    def passed(self) -> bool:
        return self.duplicate_count == 0 and self.invalid_count == 0 and self.missing_close_count == 0 and self.date_out_of_range_count == 0


def validate_daily_rows(
    rows: Iterable[Mapping[str, Any]], *, start_date: date, end_date: date
) -> DataQualityReport:
    seen: set[tuple[str, str]] = set()
    count = duplicates = invalid = missing_close = out_of_range = 0
    for row in rows:
        count += 1
        symbol = str(row.get("symbol", "")).strip()
        raw_date = str(row.get("trade_date", ""))
        try:
            trade_date = date.fromisoformat(raw_date)
            if not start_date <= trade_date <= end_date:
                out_of_range += 1
        except ValueError:
            out_of_range += 1
            trade_date = None
        key = (symbol, raw_date)
        if key in seen:
            duplicates += 1
        seen.add(key)

        close = row.get("close")
        if close is None:
            missing_close += 1
        numeric: dict[str, float] = {}
        for field in ("open", "high", "low", "close", "adjusted_close", "volume"):
            value = row.get(field)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                invalid += 1
            else:
                numeric[field] = float(value)
        if "high" in numeric and "low" in numeric and numeric["high"] < numeric["low"]:
            invalid += 1
        if "high" in numeric and any(numeric.get(field, numeric["high"]) > numeric["high"] for field in ("open", "close")):
            invalid += 1
        if "low" in numeric and any(numeric.get(field, numeric["low"]) < numeric["low"] for field in ("open", "close")):
            invalid += 1
        if not symbol:
            invalid += 1
    return DataQualityReport(count, duplicates, invalid, missing_close, out_of_range)
