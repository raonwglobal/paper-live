from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from .data_lake import DatasetManifest, GoogleDriveStorageAgent
from .execution_audit import ExecutionAuditTrail
from .ingestion_pipeline import IngestionPipeline, IngestionPipelineResult
from .ingestion_run import IngestionRunLedger
from .market_dataset import DailyDatasetBuilder, DailyPriceProvider
from .recommendation_pipeline import RecommendationPipeline
from .run_manifest import RunArtifact, RunManifestTracker, build_run_manifest_v3
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
                 recommendation_pipeline: RecommendationPipeline | None = None,
                 manifest_tracker: RunManifestTracker | None = None,
                 audit_trail: ExecutionAuditTrail | None = None) -> None:
        self.storage = storage
        self.manifest_tracker = manifest_tracker or RunManifestTracker(writer=storage)
        self.audit_trail = audit_trail
        if self.audit_trail is not None and self.audit_trail.manifest_tracker is None:
            self.audit_trail.manifest_tracker = self.manifest_tracker
        if self.audit_trail is not None and self.audit_trail.writer is None:
            self.audit_trail.writer = storage.client
            self.audit_trail.folder_id = storage.folder_id
        self.ingestion = IngestionPipeline(
            universe, provider_factory, DailyDatasetBuilder(storage), ledger=ledger,
            batch_size=batch_size, requests_per_second=requests_per_second,
            max_retries=max_retries, backoff_seconds=backoff_seconds, sleeper=sleeper,
        )
        self.recommendations = recommendation_pipeline or RecommendationPipeline(storage=storage)

    @staticmethod
    def _manifest(*, ingestion: IngestionPipelineResult, decision_time: str,
                  ranked: tuple[dict, ...] = (), feature_manifest: DatasetManifest | None = None,
                  recommendation_manifest: DatasetManifest | None = None):
        selected = [row for row in ranked if bool(row.get("portfolio_selected"))]
        target_weight_sum = sum(float(row.get("target_weight", 0.0)) for row in selected)
        portfolio = None
        return selected, target_weight_sum, build_run_manifest_v3(
            run_id=ingestion.manifest.run_id,
            status=ingestion.manifest.status,
            decision_time=decision_time,
            ingestion=RunArtifact(
                stage="ingestion", artifact_id=ingestion.manifest_artifact_id,
                dataset=ingestion.manifest.dataset, row_count=ingestion.manifest.rows_collected,
                checksum_sha256=ingestion.manifest.dataset_checksum_sha256,
                status=ingestion.manifest.status,
                metadata={
                    "requested_symbols": ingestion.manifest.requested_symbols,
                    "succeeded_symbols": ingestion.manifest.succeeded_symbols,
                    "failed_symbols": ingestion.manifest.failed_symbols,
                    "failure_artifact_id": ingestion.failure_artifact_id,
                },
            ),
            features=RunArtifact(
                stage="features", dataset=feature_manifest.dataset if feature_manifest else None,
                row_count=feature_manifest.row_count if feature_manifest else 0,
                checksum_sha256=feature_manifest.checksum_sha256 if feature_manifest else None,
                status="completed" if feature_manifest else "not_run",
            ),
            recommendations=RunArtifact(
                stage="recommendations", dataset=recommendation_manifest.dataset if recommendation_manifest else None,
                row_count=recommendation_manifest.row_count if recommendation_manifest else 0,
                checksum_sha256=recommendation_manifest.checksum_sha256 if recommendation_manifest else None,
                status="completed" if recommendation_manifest else "not_run",
                metadata={"candidate_quality": {}},
            ),
            portfolio=RunArtifact(stage="portfolio", row_count=len(selected),
                                  status="completed" if ranked else "not_run",
                                  metadata={"selected_count": len(selected),
                                            "target_weight_sum": round(target_weight_sum, 6), "config": {}}),
            risk=RunArtifact(stage="risk", status="not_run"),
            execution_audit=RunArtifact(stage="execution_audit", status="not_run"),
            fill=RunArtifact(stage="fill", status="not_run"),
            pnl=RunArtifact(stage="pnl", status="not_run"),
            reflection=RunArtifact(stage="reflection", status="not_run"),
        )

    def _persist_audit(self, run_id: str) -> str | None:
        if self.audit_trail is None or not self.audit_trail.records:
            return None
        return self.audit_trail.persist(run_id=run_id)

    def run(self, *, start_date: date, end_date: date, decision_time: str,
            available_at: str | None = None) -> DailyRecommendationJobResult:
        ingestion_available_at = available_at or decision_time
        ingestion = self.ingestion.run(
            start_date=start_date, end_date=end_date, available_at=ingestion_available_at
        )

        # Register immediately after ingestion so downstream failures leave a durable failed run marker.
        _, _, initial_manifest = self._manifest(ingestion=ingestion, decision_time=decision_time)
        self.manifest_tracker.register(initial_manifest, persist=False)

        ranked: tuple[dict, ...] = ()
        feature_manifest = recommendation_manifest = None
        try:
            if ingestion.rows:
                ranked_list, feature_manifest, recommendation_manifest = self.recommendations.build_from_daily(
                    [row.as_row() for row in ingestion.rows], decision_time=decision_time
                )
                ranked = tuple(ranked_list)

            selected, target_weight_sum, manifest = self._manifest(
                ingestion=ingestion, decision_time=decision_time, ranked=ranked,
                feature_manifest=feature_manifest, recommendation_manifest=recommendation_manifest,
            )
            portfolio = self.recommendations.portfolio
            manifest = manifest.with_stage(RunArtifact(
                stage="recommendations", dataset=manifest.stage("recommendations").dataset,
                row_count=manifest.stage("recommendations").row_count,
                checksum_sha256=manifest.stage("recommendations").checksum_sha256,
                status=manifest.stage("recommendations").status,
                metadata={
                    "candidate_quality": dict(self.recommendations.last_filter_stats),
                    "filter_audit_dataset": self.recommendations.last_filter_audit_manifest.dataset if self.recommendations.last_filter_audit_manifest else None,
                    "filter_audit_checksum_sha256": self.recommendations.last_filter_audit_manifest.checksum_sha256 if self.recommendations.last_filter_audit_manifest else None,
                },
            ))
            manifest = manifest.with_stage(RunArtifact(
                stage="portfolio", row_count=len(selected), status="completed" if ranked else "not_run",
                metadata={
                    "selected_count": len(selected), "target_weight_sum": round(target_weight_sum, 6),
                    "config": {
                        "max_positions": portfolio.max_positions,
                        "max_positions_per_market": portfolio.max_positions_per_market,
                        "min_score": portfolio.min_score,
                        "min_confidence": portfolio.min_confidence,
                        "max_weight": portfolio.max_weight,
                    },
                },
            ))
            self.manifest_tracker.register(manifest, persist=False)
            audit_uri = self._persist_audit(ingestion.manifest.run_id)
            final = self.manifest_tracker.finalize(ingestion.manifest.run_id, status="completed", audit_uri=audit_uri)
            return DailyRecommendationJobResult(
                ingestion, ranked, feature_manifest, recommendation_manifest, final.manifest_uri
            )
        except Exception:
            # Commit-last semantics: a failed run is made visible after any in-memory/audit work above fails.
            try:
                audit_uri = self._persist_audit(ingestion.manifest.run_id)
                self.manifest_tracker.finalize(ingestion.manifest.run_id, status="failed", audit_uri=audit_uri)
            finally:
                raise
