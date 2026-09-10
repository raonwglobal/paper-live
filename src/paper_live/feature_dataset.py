from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from typing import Iterable, Mapping, Any

from .recommendation import StockRecommendationAgent


class FeatureDatasetService:
    """Builds an auditable recommendation snapshot from point-in-time feature rows."""

    def __init__(self, recommender: StockRecommendationAgent | None = None):
        self.recommender = recommender or StockRecommendationAgent()

    def rank(self, rows: Iterable[Mapping[str, Any]], *, data_as_of: str) -> list[dict[str, Any]]:
        ranked = self.recommender.rank(list(rows), data_as_of=data_as_of)
        for item in ranked:
            item["snapshot_checksum"] = self.checksum(item)
        return ranked

    @staticmethod
    def checksum(row: Mapping[str, Any]) -> str:
        payload = json.dumps(dict(row), sort_keys=True, separators=(",", ":"), default=str).encode()
        return hashlib.sha256(payload).hexdigest()
