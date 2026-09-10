from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256
import json
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
        ranked = self.feature_service.rank(features, data_as_of=decision_time)
        for row in ranked:
            row["decision_time"] = decision_time
            row["dataset_version"] = "recommendation-v1"
            row["input_checksum_sha256"] = input_checksum
        recommendation_manifest = self.storage.write_snapshot(recommendation_dataset, ranked, as_of=decision_time,
                                                              schema_version="recommendation-v1")
        return ranked, feature_manifest, recommendation_manifest
