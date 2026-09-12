from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetryItem:
    market: str
    symbol: str
    start_date: str
    end_date: str
    attempts: int = 0
    last_error: str = ""


class RetryQueue:
    """In-memory bounded queue; persistence can be supplied by the orchestration layer."""

    def __init__(self, *, max_attempts: int = 3):
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self.max_attempts = max_attempts
        self._items: dict[tuple[str, str, str, str], RetryItem] = {}

    def enqueue(self, item: RetryItem) -> bool:
        key = (item.market, item.symbol, item.start_date, item.end_date)
        if item.attempts >= self.max_attempts:
            return False
        current = self._items.get(key)
        if current is None or item.attempts > current.attempts:
            self._items[key] = item
            return True
        return False

    def record_failure(self, item: RetryItem, error: Exception | str) -> bool:
        next_item = RetryItem(
            item.market, item.symbol, item.start_date, item.end_date,
            attempts=item.attempts + 1,
            last_error=type(error).__name__ if isinstance(error, Exception) else str(error),
        )
        return self.enqueue(next_item)

    def pop_all(self) -> tuple[RetryItem, ...]:
        items = tuple(sorted(self._items.values(), key=lambda x: (x.market, x.symbol, x.start_date, x.end_date)))
        self._items.clear()
        return items

    def __len__(self) -> int:
        return len(self._items)
