from datetime import date

from paper_live.data_lake import GoogleDriveStorageAgent, LocalDriveMirror
from paper_live.ingestion_pipeline import IngestionPipeline
from paper_live.ingestion_run import IngestionRunLedger
from paper_live.market_dataset import DailyDatasetBuilder
from paper_live.universe import Security, SecurityMaster


class Provider:
    def fetch_daily_prices(self, symbol, start_date, end_date):
        return [{"symbol": symbol, "date": "20260828", "close": "100", "volume": "10"}]


def test_pipeline_creates_a_deterministic_auditable_run(tmp_path):
    universe = SecurityMaster([
        Security("000002", "B", "KRX"),
        Security("000001", "A", "KRX"),
    ])
    storage = GoogleDriveStorageAgent(LocalDriveMirror(tmp_path), folder_id="datasets")
    ledger = IngestionRunLedger(LocalDriveMirror(tmp_path), folder_id="runs")
    pipeline = IngestionPipeline(
        universe,
        lambda market: Provider(),
        DailyDatasetBuilder(storage),
        ledger=ledger,
        batch_size=1,
        requests_per_second=1000,
        sleeper=lambda _: None,
    )
    result = pipeline.run(start_date=date(2026, 8, 28), end_date=date(2026, 8, 28), available_at="2026-08-28T18:00:00+09:00")
    assert result.manifest.status == "completed"
    assert result.manifest.requested_symbols == 2
    assert result.manifest.succeeded_symbols == 2
    assert result.manifest.rows_collected == 2
    assert result.manifest_artifact_id
    assert result.failure_artifact_id
