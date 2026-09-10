from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable

from .ingestion_job import MarketIngestionJob
from .ingestion_run import FailureQueue, IngestionFailure, IngestionRunLedger, IngestionRunManifest, build_manifest, utc_now
from .market_dataset import DailyPriceProvider
from .market_ingestion import IngestionFailure as CollectorFailure
from .universe import SecurityMaster


@dataclass(frozen=True)
class IngestionPipelineResult:
    manifest: IngestionRunManifest
    failures: FailureQueue
    manifest_artifact_id: str | None = None
    failure_artifact_id: str | None = None
    dataset_manifest: object | None = None


class IngestionPipeline:
    """Canonical data ingestion boundary: collect -> publish -> ledger."""

    def __init__(self, universe: SecurityMaster, provider_factory: Callable[[str], DailyPriceProvider], builder,
                 *, ledger: IngestionRunLedger | None = None, batch_size: int = 200,
                 requests_per_second: float = 2.0, max_retries: int = 3,
                 backoff_seconds: float = 1.0, sleeper=None) -> None:
        self.universe = universe
        self.ledger = ledger
        self.job = MarketIngestionJob(universe, provider_factory, builder, batch_size=batch_size,
                                      requests_per_second=requests_per_second, max_retries=max_retries,
                                      backoff_seconds=backoff_seconds, sleeper=sleeper)

    def run(self, *, start_date: date, end_date: date, available_at: str | None = None) -> IngestionPipelineResult:
        securities = self.universe.active()
        symbols = [security.symbol for security in securities]
        markets = sorted({security.market for security in securities})
        started = utc_now()
        report = self.job.run(start_date=start_date, end_date=end_date, available_at=available_at)
        failures = FailureQueue(
            IngestionFailure(market=market, symbol=failure.symbol, start_date=start_date.isoformat(),
                             end_date=end_date.isoformat(), error_type=type(failure).__name__,
                             error_message=failure.error, attempts=failure.attempts, retryable=True)
            for market, failure in report.failure_details
            if isinstance(failure, CollectorFailure)
        )
        dataset = report.dataset_manifest
        run_id = IngestionRunLedger.new_run_id(market=','.join(markets), start_date=start_date,
                                               end_date=end_date, symbols=symbols)
        manifest = build_manifest(run_id=run_id, started_at=started, market=','.join(markets),
                                  start_date=start_date, end_date=end_date,
                                  requested_symbols=len(set(symbols)), succeeded_symbols=report.symbols_ok,
                                  rows_collected=report.records, failures=failures,
                                  dataset=getattr(dataset, "dataset", None),
                                  dataset_checksum_sha256=getattr(dataset, "checksum_sha256", None),
                                  finished_at=report.completed_at)
        if self.ledger:
            manifest_id, failure_id = self.ledger.write(manifest, failures)
            return IngestionPipelineResult(manifest, failures, manifest_id, failure_id, dataset)
        return IngestionPipelineResult(manifest, failures, dataset_manifest=dataset)
