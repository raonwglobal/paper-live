from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from math import isfinite
from typing import Any

from .data_lake import DatasetManifest, GoogleDriveStorageAgent
from .feature_dataset import FeatureDatasetService
from .features import DailyFeatureEngine
from .recommendation import StockRecommendationAgent


@dataclass(frozen=True)
class PortfolioConfig:
    max_positions: int = 10
    max_positions_per_market: int = 5
    min_score: float = 50.0
    min_confidence: float = 40.0
    max_weight: float = 0.25

    def __post_init__(self) -> None:
        if self.max_positions < 1 or self.max_positions_per_market < 1:
            raise ValueError("portfolio position limits must be positive")
        if not 0 <= self.min_score <= 100 or not 0 <= self.min_confidence <= 100:
            raise ValueError("portfolio score thresholds must be between 0 and 100")
        if not 0 < self.max_weight <= 1:
            raise ValueError("portfolio max_weight must be in (0, 1]")


@dataclass(frozen=True)
class PitValidationReport:
    input_rows: int
    eligible_rows: int
    rejected_rows: int
    rejected_missing_timestamp: int
    rejected_future_timestamp: int


class PointInTimeValidator:
    """Validate that observations were available no later than decision time."""

    def validate(self, rows: Sequence[dict[str, Any]], *, decision_time: str) -> tuple[list[dict[str, Any]], PitValidationReport]:
        decision = RecommendationPipeline._parse_aware(decision_time)
        if decision is None:
            raise ValueError("decision_time must be timezone-aware ISO-8601")
        eligible: list[dict[str, Any]] = []
        missing = 0
        future = 0
        for row in rows:
            raw = row.get("available_at")
            if not isinstance(raw, str) or not raw:
                missing += 1
                continue
            available = RecommendationPipeline._parse_aware(raw)
            if available is None:
                missing += 1
                continue
            if available > decision:
                future += 1
                continue
            eligible.append(dict(row))
        return eligible, PitValidationReport(len(rows), len(eligible), len(rows) - len(eligible), missing, future)


class RecommendationPipeline:
    """Build deterministic PIT features, recommendations, and a diversified portfolio."""

    def __init__(self, agent: StockRecommendationAgent | None = None,
                 storage: GoogleDriveStorageAgent | None = None,
                 feature_engine: DailyFeatureEngine | None = None,
                 *, min_history: int = 2, min_volume: float = 1.0,
                 max_abs_return_1d: float = 0.50, max_volatility: float = 0.20,
                 portfolio: PortfolioConfig | None = None):
        if storage is None:
            raise ValueError("storage is required")
        if min_history < 1 or min_volume < 0 or max_abs_return_1d <= 0 or max_volatility <= 0:
            raise ValueError("invalid recommendation quality thresholds")
        self.agent = agent or StockRecommendationAgent()
        self.storage = storage
        self.feature_engine = feature_engine or DailyFeatureEngine()
        self.feature_service = FeatureDatasetService(self.agent)
        self.pit_validator = PointInTimeValidator()
        self.min_history = min_history
        self.min_volume = min_volume
        self.max_abs_return_1d = max_abs_return_1d
        self.max_volatility = max_volatility
        self.portfolio = portfolio or PortfolioConfig()
        self.last_filter_stats: dict[str, int] = {"pit_eligible": 0, "latest_candidates": 0, "selected_candidates": 0, "filtered_history": 0, "filtered_volume": 0, "filtered_return": 0, "filtered_volatility": 0, "filtered_ohlc": 0}
        self.last_filter_audit: list[dict[str, Any]] = []
        self.last_filter_audit_manifest: DatasetManifest | None = None

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
        latest: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            if not cls._is_point_in_time(row, decision_time):
                continue
            symbol = str(row.get("symbol", "")).strip()
            if not symbol:
                continue
            key = (str(row.get("market", "")), symbol)
            current = latest.get(key)
            if current is None or (str(row.get("trade_date", "")), str(row.get("available_at", ""))) > (str(current.get("trade_date", "")), str(current.get("available_at", ""))):
                latest[key] = row
        return sorted(latest.values(), key=lambda r: (str(r.get("market", "")), str(r.get("symbol", "")), str(r.get("trade_date", ""))))

    @classmethod
    def _history_counts(cls, rows: Sequence[dict[str, Any]], *, decision_time: str) -> dict[tuple[str, str], int]:
        counts: dict[tuple[str, str], int] = {}
        for row in rows:
            if not cls._is_point_in_time(row, decision_time):
                continue
            symbol = str(row.get("symbol", "")).strip()
            if symbol:
                key = (str(row.get("market", "")), symbol)
                counts[key] = counts.get(key, 0) + 1
        return counts

    def _filter_candidates(self, candidates: Sequence[dict[str, Any]], *, history_counts: dict[tuple[str, str], int]) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        audit: list[dict[str, Any]] = []
        stats = {"filtered_history": 0, "filtered_volume": 0, "filtered_return": 0, "filtered_volatility": 0, "filtered_ohlc": 0}
        for row in candidates:
            key = (str(row.get("market", "")), str(row.get("symbol", "")))
            if history_counts.get(key, 0) < self.min_history:
                stats["filtered_history"] += 1
                audit.append(self._filter_audit_row(row, "insufficient_history"))
                continue
            volume_raw = row.get("volume")
            try:
                volume_value = float(str(volume_raw)) if volume_raw is not None else 0.0
            except (TypeError, ValueError):
                volume_value = 0.0
            if not isfinite(volume_value) or volume_value < self.min_volume:
                stats["filtered_volume"] += 1
                audit.append(self._filter_audit_row(row, "invalid_or_low_volume"))
                continue
            if row.get("return_1d") is not None:
                try:
                    return_value = float(str(row["return_1d"]))
                except (TypeError, ValueError):
                    return_value = float("inf")
                if not isfinite(return_value) or abs(return_value) > self.max_abs_return_1d:
                    stats["filtered_return"] += 1
                    audit.append(self._filter_audit_row(row, "return_limit"))
                    continue
            if row.get("volatility") is not None:
                try:
                    volatility_value = float(str(row["volatility"]))
                except (TypeError, ValueError):
                    volatility_value = float("inf")
                if not isfinite(volatility_value) or volatility_value > self.max_volatility:
                    stats["filtered_volatility"] += 1
                    audit.append(self._filter_audit_row(row, "volatility_limit"))
                    continue
            try:
                numeric = {key: (None if row.get(key) is None else float(str(row[key]))) for key in ("open", "high", "low", "close")}
            except (TypeError, ValueError):
                stats["filtered_ohlc"] += 1
                continue
            if any(value is not None and not isfinite(value) for value in numeric.values()):
                stats["filtered_ohlc"] += 1
                continue
            open_value, high_value, low_value, close_value = (numeric[key] for key in ("open", "high", "low", "close"))
            if close_value is None or close_value <= 0 or (high_value is not None and high_value < max(x for x in (open_value, close_value) if x is not None)) or (low_value is not None and low_value > min(x for x in (open_value, close_value) if x is not None)):
                stats["filtered_ohlc"] += 1
                audit.append(self._filter_audit_row(row, "invalid_ohlc"))
                continue
            selected.append(row)
        self.last_filter_stats.update(stats)
        self.last_filter_audit = audit
        self.last_filter_stats["selected_candidates"] = len(selected)
        return selected

    @staticmethod
    def _filter_audit_row(row: Mapping[str, Any], reason: str) -> dict[str, Any]:
        return {"market": str(row.get("market", "")), "symbol": str(row.get("symbol", "")), "trade_date": row.get("trade_date"), "available_at": row.get("available_at"), "reason": reason}

    @staticmethod
    def _number(value: Any, default: float = 0.0) -> float:
        if value is None:
            return default
        try:
            number = float(str(value))
        except (TypeError, ValueError):
            return default
        return number if isfinite(number) else default

    def construct_portfolio(self, ranked: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        """Select and weight candidates with market caps and inverse-volatility sizing."""
        for row in ranked:
            row["portfolio_selected"] = False
            row["portfolio_rank"] = None
            row["target_weight"] = 0.0
        eligible = [row for row in ranked if self._number(row.get("score")) >= self.portfolio.min_score and self._number(row.get("confidence")) >= self.portfolio.min_confidence]
        selected: list[dict[str, Any]] = []
        market_counts: dict[str, int] = {}
        for row in eligible:
            market = str(row.get("market", ""))
            if market_counts.get(market, 0) >= self.portfolio.max_positions_per_market:
                continue
            selected.append(row)
            market_counts[market] = market_counts.get(market, 0) + 1
            if len(selected) >= self.portfolio.max_positions:
                break
        raw_weights = [1.0 / max(self._number(row.get("volatility"), 0.01), 0.01) for row in selected]
        total = sum(raw_weights)
        if not total:
            return [dict(row) for row in ranked]
        weights = [value / total for value in raw_weights]
        for row, weight, position in zip(selected, weights, range(1, len(selected) + 1), strict=True):
            row["portfolio_selected"] = True
            row["portfolio_rank"] = position
            row["target_weight"] = round(min(weight, self.portfolio.max_weight), 6)
        return [dict(row) for row in ranked]

    @staticmethod
    def _bounded_score(value: Any, scale: float = 1.0, *, inverse: bool = False) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 50.0
        direction = -1.0 if inverse else 1.0
        return round(max(0.0, min(100.0, 50.0 + 50.0 * number * scale * direction)), 4)

    def _factorize(self, row: dict[str, Any]) -> dict[str, Any]:
        result = dict(row)
        result.setdefault("fundamental_score", 50.0)
        result.setdefault("value_score", 50.0)
        result.setdefault("quality_score", 50.0)
        result.setdefault("sentiment_score", 50.0)
        result["momentum_score"] = self._bounded_score(result.get("momentum"))
        result["technical_score"] = self._bounded_score(result.get("return_1d"))
        result["risk_score"] = self._bounded_score(result.get("volatility"), inverse=True)
        return result

    def run(self, feature_rows: Sequence[dict[str, Any]], *, data_as_of: str, dataset: str = "recommendations/daily") -> tuple[list[dict[str, Any]], DatasetManifest]:
        ranked = self.agent.rank(feature_rows, data_as_of=data_as_of)
        input_checksum = self._checksum(feature_rows)
        for row in ranked:
            row["decision_time"] = data_as_of
            row["dataset_version"] = "recommendation-v1"
            row["input_checksum_sha256"] = input_checksum
        manifest = self.storage.write_jsonl(dataset, ranked, as_of=data_as_of, schema_version="recommendation-v1")
        return ranked, manifest

    def build_from_daily(self, daily_rows: Sequence[dict[str, Any]], *, decision_time: str, feature_dataset: str = "features/daily", recommendation_dataset: str = "recommendations/daily") -> tuple[list[dict[str, Any]], DatasetManifest, DatasetManifest]:
        ordered = sorted((dict(row) for row in daily_rows), key=lambda r: (str(r.get("market", "")), str(r.get("symbol", "")), str(r.get("trade_date", ""))))
        input_checksum = self._checksum(ordered)
        pit_rows, pit_report = self.pit_validator.validate(ordered, decision_time=decision_time)
        features = self.feature_engine.build(pit_rows, decision_time=decision_time)
        for row in features:
            row["input_checksum_sha256"] = input_checksum
        feature_manifest = self.storage.write_snapshot(feature_dataset, features, as_of=decision_time, schema_version="daily-features-v1")
        self.last_filter_stats = {"pit_eligible": pit_report.eligible_rows, "pit_rejected": pit_report.rejected_rows, "pit_missing_timestamp": pit_report.rejected_missing_timestamp, "pit_future_timestamp": pit_report.rejected_future_timestamp, "latest_candidates": 0, "selected_candidates": 0, "filtered_history": 0, "filtered_volume": 0, "filtered_return": 0, "filtered_volatility": 0, "filtered_ohlc": 0}
        candidates = self._latest_candidates(features, decision_time=decision_time)
        self.last_filter_stats["latest_candidates"] = len(candidates)
        history_counts = self._history_counts(features, decision_time=decision_time)
        filtered_rows = self._filter_candidates(candidates, history_counts=history_counts)
        filter_audit = [{**row, "decision_time": decision_time, "input_checksum_sha256": input_checksum} for row in self.last_filter_audit]
        self.last_filter_audit_manifest = self.storage.write_snapshot("recommendations/daily_filter_audit", filter_audit, as_of=decision_time, schema_version="recommendation-filter-audit-v1")
        factor_rows = [self._factorize(row) for row in filtered_rows]
        ranked = self.feature_service.rank(factor_rows, data_as_of=decision_time)
        selected_by_identity = {(str(row.get("market", "")), str(row.get("symbol", ""))): row for row in candidates}
        for row in ranked:
            row["decision_time"] = decision_time
            row["dataset_version"] = "recommendation-v1"
            row["input_checksum_sha256"] = input_checksum
            selected = selected_by_identity.get((str(row.get("market", "")), str(row.get("symbol", ""))))
            if selected is not None:
                row["trade_date"] = selected.get("trade_date")
                row["market"] = selected.get("market")
                row["feature_available_at"] = selected.get("available_at")
                row["volatility"] = selected.get("volatility")
        ranked = self.construct_portfolio(ranked)
        recommendation_manifest = self.storage.write_snapshot(recommendation_dataset, ranked, as_of=decision_time, schema_version="recommendation-v1")
        return ranked, feature_manifest, recommendation_manifest
