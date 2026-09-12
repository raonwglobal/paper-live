from datetime import date

from paper_live.daily_recommendation_job import DailyRecommendationJob
from paper_live.data_lake import GoogleDriveStorageAgent, LocalDriveMirror
from paper_live.universe import Security, SecurityMaster


class Provider:
    def fetch_daily_prices(self, symbol, start_date, end_date):
        return [
            {"symbol": symbol, "date": "20260827", "close": "100", "volume": "100"},
            {"symbol": symbol, "date": "20260828", "close": "110", "volume": "120"},
        ]


def test_daily_job_connects_ingestion_features_and_recommendations(tmp_path):
    storage = GoogleDriveStorageAgent(LocalDriveMirror(tmp_path), folder_id="datasets")
    universe = SecurityMaster([Security("000001", "A", "KRX")])
    job = DailyRecommendationJob(universe, lambda market: Provider(), storage,
                                 requests_per_second=1000, sleeper=lambda _: None)
    result = job.run(start_date=date(2026, 8, 27), end_date=date(2026, 8, 28),
                     decision_time="2026-08-28T19:00:00+09:00")
    assert result.ingestion.manifest.status == "completed"
    assert result.feature_manifest and result.feature_manifest.row_count == 2
    assert result.recommendation_manifest and result.recommendation_manifest.row_count == 2
    assert result.ranked[0]["rank"] == 1
    assert result.run_artifact_id
