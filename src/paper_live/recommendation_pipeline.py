from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from hashlib import sha256
from typing import Any

from .data_lake import DatasetManifest, GoogleDriveStorageAgent
from .feature_dataset import FeatureDatasetService
from .features import DailyFeatureEngine
from .recommendation import StockRecommendationAgent


class RecommendationPipeline:
    """Build and persist deterministic, point-in-time feature/recommendation snapshots."""

    def __init__(self, agent: StockRecommendationAgent | None = None,
                 storage: GoogleDriveStorageAgent | None = None,
                 feature_engine: DailyFeatureEngine | None = None):
        if storage is None:
            raise ValueError("storage is required")
        self.agent = agent or StockRecommendationAgent()
        self.storage = storage
        self.feature_engine = feature_engine or DailyFeatureEngine()
        self.feature_service = FeatureDatasetService(self.agent)

    @staticmethod
    def _checksum(rows: Sequence[dict[str, Any]]) -> str:
        payload = json.dumps(list(rows), sort_keys=True, separators=(",", ":"), default=str).encode()
        return sha256(payload).hexdigest()

    @staticmethod
    def _parse_aware(value: Any) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None

    @classmethod
    def _is_point_in_time(cls, row: dict[str, Any], decision_time: str) -> bool:
        available_at = row.get("available_at")
        if available_at is None:
            return True
        available = cls._parse_aware(available_at)
        decision = cls._parse_aware(decision_time)
        if available is None or decision is None:
            return False
        return available <= decision

    @classmethod
    def _latest_candidates(cls, rows: Sequence[dict[str, Any]], *, decision_time: str) -> list[dict[str, Any]]:
        """Keep one latest PIT-eligible feature row per market/symbol."""
        latest: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            if not cls._is_point_in_time(row, decision_time):
                continue
            symbol = str(row.get("symbol", ""))
            if not symbol:
                continue
            key = (str(row.get("market", "")), symbol)
            current = latest.get(key)
            if current is None or (
                str(row.get("trade_date", "")), str(row.get("available_at", ""))
            ) > (
                str(current.get("trade_date", "")), str(current.get("available_at", ""))
            ):
                latest[key] = row
        return sorted(latest.values(), key=lambda r: (
            str(r.get("market", "")), str(r.get("symbol", "")), str(r.get("trade_date", ""))
        ))

    @staticmethod
    def _bounded_score(value: Any, scale: float = 1.0, *, inverse: bool = False) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 50.0
        direction = -1.0 if inverse else 1.0
        score = 50.0 + 50.0 * number * scale * direction
        return round(max(0.0, min(100.0, score)), 4)

    def _factorize(self, row: dict[str, Any]) -> dict[str, Any]:
        """Project normalized daily features into stable 0..100 recommendation factors."""
        result = dict(row)
        result.setdefault("fundamental_score", 50.0)
        result.setdefault("value_score", 50.0)
        result.setdefault("quality_score", 50.0)
        result.setdefault("sentiment_score", 50.0)
        result["momentum_score"] = self._bounded_score(result.get("momentum"))
        result["technical_score"] = self._bounded_score(result.get("return_1d"))
        result["risk_score"] = self._bounded_score(result.get("volatility"), inverse=True)
        return result

    def run(self, feature_rows: Sequence[dict[str, Any]], *, data_as_of: str,
            dataset: str = "recommendations/daily") -> tuple[list[dict[str, Any]], DatasetManifest]:
        ranked = self.agent.rank(feature_rows, data_as_of=data_as_of)
        input_checksum = self._checksum(feature_rows)
        for row in ranked:
            row["decision_time"] = data_as_of
            row["dataset_version"] = "recommendation-v1"
            row["input_checksum_sha256"] = input_checksum
        manifest = self.storage.write_jsonl(dataset, ranked, as_of=data_as_of, schema_version="recommendation-v1")
        return ranked, manifest

    def build_from_daily(self, daily_rows: Sequence[dict[str, Any]], *, decision_time: str,
                         feature_dataset: str = "features/daily",
                         recommendation_dataset: str = "recommendations/daily") -> tuple[list[dict[str, Any]], DatasetManifest, DatasetManifest]:
        ordered = sorted((dict(row) for row in daily_rows),
                         key=lambda r: (str(r.get("market", "")), str(r.get("symbol", "")), str(r.get("trade_date", ""))))
        input_checksum = self._checksum(ordered)
        features = self.feature_engine.build(ordered, decision_time=decision_time)
        for row in features:
            row["input_checksum_sha256"] = input_checksum
        feature_manifest = self.storage.write_snapshot(feature_dataset, features, as_of=decision_time,
                                                        schema_version="daily-features-v1")
        factor_rows = [self._factorize(row) for row in self._latest_candidates(features, decision_time=decision_time)]
        ranked = self.feature_service.rank(factor_rows, data_as_of=decision_time)
        for row in ranked:
            row["decision_time"] = decision_time
            row["dataset_version"] = "recommendation-v1"
            row["input_checksum_sha256"] = input_checksum
        recommendation_manifest = self.storage.write_snapshot(recommendation_dataset, ranked, as_of=decision_time,
                                                              schema_version="recommendation-v1")
        return ranked, feature_manifest, recommendation_manifest
