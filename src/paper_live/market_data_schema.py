from __future__ import annotations  # noqa: I001

from collections.abc import Iterable, Mapping
from datetime import date, datetime
from typing import Any


REQUIRED_FIELDS = ("symbol", "market", "trade_date")


def validate_daily_market_schema(rows: Iterable[Mapping[str, Any]]) -> tuple[str, ...]:
    """Return deterministic validation errors for required market-data identity fields."""
    errors: list[str] = []
    for index, row in enumerate(rows):
        symbol = str(row.get("symbol", "")).strip()
        market = str(row.get("market", "")).strip()
        trade_date = str(row.get("trade_date", "")).strip()
        if not symbol:
            errors.append(f"row[{index}]: symbol is required")
        if not market:
            errors.append(f"row[{index}]: market is required")
        try:
            date.fromisoformat(trade_date)
        except ValueError:
            errors.append(f"row[{index}]: trade_date must be YYYY-MM-DD")
        effective_date = row.get("effective_date")
        if effective_date is not None and str(effective_date) != trade_date:
            errors.append(f"row[{index}]: effective_date must match trade_date")
        available_at = row.get("available_at")
        if available_at is not None:
            try:
                parsed = datetime.fromisoformat(str(available_at).replace("Z", "+00:00"))
            except ValueError:
                errors.append(f"row[{index}]: available_at must be ISO-8601")
            else:
                if parsed.tzinfo is None or parsed.utcoffset() is None:
                    errors.append(f"row[{index}]: available_at must include timezone")
    return tuple(errors)
