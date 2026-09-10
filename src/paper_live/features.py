from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import log
from typing import Any
from datetime import datetime, timezone


@dataclass(frozen=True)
class FeatureConfig:
    momentum_window: int = 20
    volatility_window: int = 20
    volume_window: int = 20


class DailyFeatureEngine:
    """Point-in-time feature builder. Input must be sorted by symbol/trade_date."""

    def __init__(self, config: FeatureConfig | None = None):
        self.config = config or FeatureConfig()
        if min(self.config.momentum_window, self.config.volatility_window, self.config.volume_window) < 1:
            raise ValueError("feature windows must be positive")

    def build(self, rows: Sequence[Mapping[str, Any]], *, decision_time: str) -> list[dict[str, Any]]:
        groups: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
        for row in rows:
            if str(row.get("available_at", "")) <= decision_time:
                groups[(str(row.get("market", "")), str(row.get("symbol", "")))].append(row)
        output = []
        for (_market, _symbol), items in groups.items():
            items = sorted(items, key=lambda x: str(x.get("trade_date", "")))
            closes = [float(x["close"]) for x in items]
            vols = [float(x["volume"]) for x in items if x.get("volume") not in (None, "")]
            for i, row in enumerate(items):
                price = closes[i]
                prev = closes[i - 1] if i else None
                momentum = (
                    None
                    if i < self.config.momentum_window or closes[i - self.config.momentum_window] == 0
                    else price / closes[i - self.config.momentum_window] - 1
                )
                returns = [
                    log(closes[j] / closes[j - 1])
                    for j in range(max(1, i - self.config.volatility_window + 1), i + 1)
                    if closes[j] > 0 and closes[j - 1] > 0
                ]
                volatility = (
                    (sum((x - (sum(returns) / len(returns))) ** 2 for x in returns) / len(returns)) ** 0.5
                    if returns
                    else None
                )
                volume = float(row["volume"]) if row.get("volume") not in (None, "") else None
                recent = vols[max(0, len(vols) - self.config.volume_window) :]
                avg_vol = sum(recent) / len(recent) if recent else None
                output.append(
                    {
                        **row,
                        "return_1d": None if prev is None or prev == 0 else price / prev - 1,
                        "momentum": momentum,
                        "volatility": volatility,
                        "volume_ratio": None if not volume or not avg_vol else volume / avg_vol,
                        "feature_decision_time": decision_time,
                        "feature_version": "daily-features-v1",
                    }
                )
        return output
