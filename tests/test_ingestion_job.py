from datetime import date
from paper_live.ingestion_job import MarketIngestionJob
from paper_live.market_dataset import DailyDatasetBuilder
from paper_live.data_lake import GoogleDriveStorageAgent, LocalDriveMirror
from paper_live.universe import Security, SecurityMaster

class Provider:
    def fetch_daily_prices(self, symbol, start_date, end_date):
        return [{"date":"2026-08-28","close":"100"}]

def test_job_runs_all_batches(tmp_path):
    storage=GoogleDriveStorageAgent(LocalDriveMirror(tmp_path), folder_id="datasets")
    universe=SecurityMaster([Security(str(i),"N","KRX") for i in range(3)])
    job=MarketIngestionJob(universe, lambda market: Provider(), DailyDatasetBuilder(storage),
                           batch_size=2, requests_per_second=1000, sleeper=lambda _: None)
    report=job.run(start_date=date(2026,8,28), end_date=date(2026,8,28),
                   available_at="2026-08-28T18:00:00+09:00")
    assert report.records == 3
    assert report.symbols_ok == 3
    assert report.failures == 0
