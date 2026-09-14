from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from .data_lake import DatasetManifest, GoogleDriveStorageAgent
from .ingestion_pipeline import IngestionPipeline, IngestionPipelineResult
from .ingestion_run import IngestionRunLedger
from .market_dataset import DailyDatasetBuilder, DailyPriceProvider
from .recommendation_pipeline import RecommendationPipeline
from .universe import SecurityMaster


@dataclass(frozen=True)
class DailyRecommendationJobResult:
    ingestion: IngestionPipelineResult
    ranked: tuple[dict, ...]
    feature_manifest: DatasetManifest | None
    recommendation_manifest: DatasetManifest | None
    run_artifact_id: str | None


class DailyRecommendationJob:
    """Single safe orchestration boundary: universe -> data -> features -> recommendations -> audit."""

    def __init__(self, universe: SecurityMaster, provider_factory: Callable[[str], DailyPriceProvider],
                 storage: GoogleDriveStorageAgent, *, ledger: IngestionRunLedger | None = None,
                 batch_size: int = 200, requests_per_second: float = 2.0,
                 max_retries: int = 3, backoff_seconds: float = 1.0, sleeper=None,
                 recommendation_pipeline: RecommendationPipeline | None = None) -> None:
        self.storage = storage
        self.ingestion = IngestionPipeline(
            universe, provider_factory, DailyDatasetBuilder(storage), ledger=ledger,
            batch_size=batch_size, requests_per_second=requests_per_second,
            max_retries=max_retries, backoff_seconds=backoff_seconds, sleeper=sleeper,
        )
        self.recommendations = recommendation_pipeline or RecommendationPipeline(storage=storage)

    def run(self, *, start_date: date, end_date: date, decision_time: str,
            available_at: str | None = None) -> DailyRecommendationJobResult:
        ingestion_available_at = available_at or decision_time
        ingestion = self.ingestion.run(
            start_date=start_date, end_date=end_date, available_at=ingestion_available_at
        )
        ranked: tuple[dict, ...] = ()
        feature_manifest = recommendation_manifest = None
        if ingestion.rows:
            ranked_list, feature_manifest, recommendation_manifest = self.recommendations.build_from_daily(
                [row.as_row() for row in ingestion.rows], decision_time=decision_time
            )
            ranked = tuple(ranked_list)

        selected = [row for row in ranked if bool(row.get("portfolio_selected"))]
        target_weight_sum = sum(float(row.get("target_weight", 0.0)) for row in selected)
        portfolio = self.recommendations.portfolio
        run_manifest = {
            "run_id": ingestion.manifest.run_id,
            "status": ingestion.manifest.status,
            "ingestion": {
                "requested_symbols": ingestion.manifest.requested_symbols,
                "succeeded_symbols": ingestion.manifest.succeeded_symbols,
                "failed_symbols": ingestion.manifest.failed_symbols,
                "rows_collected": ingestion.manifest.rows_collected,
                "dataset_checksum_sha256": ingestion.manifest.dataset_checksum_sha256,
            },
            "features": {
                "row_count": feature_manifest.row_count if feature_manifest else 0,
                "checksum_sha256": feature_manifest.checksum_sha256 if feature_manifest else None,
            },
            "candidate_quality": {
                **self.recommendations.last_filter_stats,
                "min_history": self.recommendations.min_history,
                "min_volume": self.recommendations.min_volume,
                "max_abs_return_1d": self.recommendations.max_abs_return_1d,
                "max_volatility": self.recommendations.max_volatility,
            },
            "recommendations": {
                "row_count": recommendation_manifest.row_count if recommendation_manifest else 0,
                "checksum_sha256": recommendation_manifest.checksum_sha256 if recommendation_manifest else None,
            },
            "portfolio": {
                "selected_count": len(selected),
                "target_weight_sum": round(target_weight_sum, 6),
                "config": {
                    "max_positions": portfolio.max_positions,
                    "max_positions_per_market": portfolio.max_positions_per_market,
                    "min_score": portfolio.min_score,
                    "min_confidence": portfolio.min_confidence,
                    "max_weight": portfolio.max_weight,
                },
            },
            "decision_time": decision_time,
            "schema_version": "daily-recommendation-job-v2",
        }
        run_artifact_id = self.storage.write_run_manifest(ingestion.manifest.run_id, run_manifest)
        return DailyRecommendationJobResult(ingestion, ranked, feature_manifest, recommendation_manifest, run_artifact_id)
