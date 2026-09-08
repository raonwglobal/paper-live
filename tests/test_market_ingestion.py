from datetime import date
from paper_live.data_lake import GoogleDriveStorageAgent, LocalDriveMirror
from paper_live.market_dataset import DailyDatasetBuilder
from paper_live.market_ingestion import ResilientDailyCollector

class FlakyProvider:
    def __init__(self): self.calls = 0
    def fetch_daily_prices(self, symbol, start_date, end_date):
        self.calls += 1
        if symbol == 'BAD': raise TimeoutError()
        return [{'date': '2026-08-28', 'close': '100'}]

def test_collector_retries_and_reports_partial_failure(tmp_path):
    storage = GoogleDriveStorageAgent(LocalDriveMirror(tmp_path), folder_id='datasets')
    collector = ResilientDailyCollector(FlakyProvider(), DailyDatasetBuilder(storage), requests_per_second=1000, max_retries=2, backoff_seconds=0, sleeper=lambda _: None)
    report = collector.collect(['GOOD','BAD'], start_date=date(2026,8,28), end_date=date(2026,8,28), market='KRX', source='test', available_at='2026-08-28T18:00:00+09:00')
    assert report.records == 1 and len(report.failures) == 1 and report.failures[0].attempts == 2
