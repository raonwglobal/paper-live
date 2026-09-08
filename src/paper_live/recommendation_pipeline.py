from __future__ import annotations

from dataclasses import asdict
from typing import Any, Sequence

from .data_lake import DatasetManifest, GoogleDriveStorageAgent
from .recommendation import StockRecommendationAgent


class RecommendationPipeline:
    """Build and persist a deterministic, point-in-time recommendation snapshot."""

    def __init__(self, agent: StockRecommendationAgent, storage: GoogleDriveStorageAgent):
        self.agent, self.storage = agent, storage

    def run(
        self,
        feature_rows: Sequence[dict[str, Any]],
        *,
        data_as_of: str,
        dataset: str = "recommendations/daily",
    ) -> tuple[list[dict[str, Any]], DatasetManifest]:
        ranked = self.agent.rank(feature_rows, data_as_of=data_as_of)
        for row in ranked:
            row["decision_time"] = data_as_of
            row["dataset_version"] = "recommendation-v1"
        manifest = self.storage.write_jsonl(
            dataset, ranked, as_of=data_as_of, schema_version="recommendation-v1"
        )
        return ranked, manifest
