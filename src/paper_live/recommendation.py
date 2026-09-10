from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from math import isfinite
from typing import Any


@dataclass(frozen=True)
class Recommendation:
    symbol: str
    score: float
    rank: int
    grade: str
    confidence: float
    reasons: tuple[str, ...]
    model_version: str = "factor-v1"
    data_as_of: str = ""


class StockRecommendationAgent:
    """Deterministic, point-in-time-safe multi-factor screener."""

    DEFAULT_WEIGHTS = {
        "fundamental_score": 0.25, "momentum_score": 0.20, "technical_score": 0.15,
        "value_score": 0.15, "quality_score": 0.10, "sentiment_score": 0.10, "risk_score": 0.05,
    }

    def __init__(self, weights: Mapping[str, float] | None = None, *, model_version: str = "factor-v1"):
        self.weights = dict(weights or self.DEFAULT_WEIGHTS)
        total = sum(self.weights.values())
        if not self.weights or total <= 0 or abs(total - 1.0) > 1e-6:
            raise ValueError("factor weights must be positive and sum to 1.0")
        if any(value < 0 for value in self.weights.values()):
            raise ValueError("factor weights cannot be negative")
        self.model_version = model_version

    @staticmethod
    def _score(value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 50.0
        return max(0.0, min(100.0, number)) if isfinite(number) else 50.0

    def score(self, row: Mapping[str, Any], *, data_as_of: str | None = None) -> Recommendation | None:
        as_of = data_as_of or str(row.get("data_as_of", ""))
        available = str(row.get("available_at", ""))
        if as_of and available:
            try:
                decision = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
                available_dt = datetime.fromisoformat(available.replace("Z", "+00:00"))
            except ValueError:
                return None
            if decision.tzinfo is None:
                decision = decision.replace(tzinfo=UTC)
            if available_dt.tzinfo is None:
                available_dt = available_dt.replace(tzinfo=UTC)
            if available_dt > decision:
                return None
        symbol = str(row.get("symbol", "")).strip()
        if not symbol:
            return None
        weighted = sum(self._score(row.get(key)) * weight for key, weight in self.weights.items())
        values = [self._score(row.get(key)) for key in self.weights]
        dispersion = max(values) - min(values)
        present = sum(key in row for key in self.weights)
        confidence = max(0.0, min(100.0, 100.0 - dispersion * 0.45)) * (present / len(self.weights))
        reasons = tuple(key.removesuffix("_score").upper() for key in self.weights if self._score(row.get(key)) >= 70)
        return Recommendation(symbol, round(weighted, 4), 0, self.grade(weighted), round(confidence, 2), reasons,
                              self.model_version, as_of)

    @staticmethod
    def grade(score: float) -> str:
        if score >= 80:
            return "A"
        if score >= 70:
            return "B"
        if score >= 55:
            return "C"
        if score >= 40:
            return "D"
        return "E"

    def rank(self, rows: Sequence[Mapping[str, Any]], *, data_as_of: str) -> list[dict[str, Any]]:
        results = [item for item in (self.score(row, data_as_of=data_as_of) for row in rows) if item is not None]
        results.sort(key=lambda item: (-item.score, item.symbol))
        return [asdict(Recommendation(item.symbol, item.score, index, item.grade, item.confidence,
                                       item.reasons, item.model_version, item.data_as_of))
                for index, item in enumerate(results, 1)]
