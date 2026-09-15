from datetime import date
import json

import pytest

from paper_live.daily_recommendation_job import DailyRecommendationJob
from paper_live.data_lake import GoogleDriveStorageAgent, LocalDriveMirror
from paper_live.universe import Security, SecurityMaster


class Provider:
    def fetch_daily_prices(self, symbol, start_date, end_date):
        return [{"symbol": symbol, "date": "20260828", "close": "100", "volume": "100"}]


class FailingRecommendations:
    def build_from_daily(self, rows, *, decision_time):
        raise RuntimeError("recommendation failure")


def test_daily_job_finalizes_failed_manifest_after_downstream_error(tmp_path):
    storage = GoogleDriveStorageAgent(LocalDriveMirror(tmp_path), folder_id="datasets")
    universe = SecurityMaster([Security("000001", "A", "KRX")])
    job = DailyRecommendationJob(
        universe, lambda market: Provider(), storage,
        recommendation_pipeline=FailingRecommendations(), requests_per_second=1000,
        sleeper=lambda _: None,
    )

    with pytest.raises(RuntimeError, match="recommendation failure"):
        job.run(
            start_date=date(2026, 8, 28), end_date=date(2026, 8, 28),
            decision_time="2026-08-28T19:00:00+09:00",
        )

    run_files = list((tmp_path / "datasets" / "runs").glob("*.json"))
    assert len(run_files) == 1
    manifest = json.loads(run_files[0].read_text())
    assert manifest["status"] == "failed"
    assert manifest["stages"][0]["status"] == "completed"
    assert manifest["stages"][1]["status"] == "not_run"
    assert manifest["stages"][2]["status"] == "not_run"
