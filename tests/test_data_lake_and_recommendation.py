from __future__ import annotations

from pathlib import Path

import pytest

from paper_live.data_lake import GoogleDriveStorageAgent, LocalDriveMirror
from paper_live.recommendation import StockRecommendationAgent


def test_drive_snapshot_is_versioned_and_manifested(tmp_path: Path):
    mirror = LocalDriveMirror(tmp_path)
    agent = GoogleDriveStorageAgent(mirror, folder_id="paper-live")
    rows = [
        {"symbol": "005930", "close": 100, "effective_date": "2026-08-28", "available_at": "2026-08-28T18:00:00+09:00"}
    ]
    manifest = agent.write_snapshot("market/daily", rows, as_of="2026-08-28", schema_version="1.0")
    assert manifest.row_count == 1
    assert manifest.checksum_sha256
    assert (tmp_path / "paper-live" / "market/daily/date=2026-08-28/manifest.json").exists()
    agent.validate_row_timestamps(rows)


def test_drive_rejects_missing_or_invalid_point_in_time_fields(tmp_path: Path):
    agent = GoogleDriveStorageAgent(LocalDriveMirror(tmp_path))
    with pytest.raises(ValueError):
        agent.validate_row_timestamps([{"symbol": "AAPL"}])
    with pytest.raises(ValueError):
        agent.validate_row_timestamps(
            [{"symbol": "AAPL", "effective_date": "2026-08-29", "available_at": "2026-08-28T00:00:00Z"}]
        )


def test_recommendation_prevents_lookahead_and_ranks():
    agent = StockRecommendationAgent()
    rows = [
        {
            "symbol": "AAPL",
            "available_at": "2026-08-31T10:00:00Z",
            "fundamental_score": 90,
            "momentum_score": 80,
            "technical_score": 85,
            "value_score": 70,
            "quality_score": 90,
            "sentiment_score": 80,
            "risk_score": 75,
        },
        {"symbol": "BAD", "available_at": "2026-09-01T10:00:00Z", "fundamental_score": 100},
        {
            "symbol": "MSFT",
            "available_at": "2026-08-31T10:00:00Z",
            "fundamental_score": 75,
            "momentum_score": 75,
            "technical_score": 75,
            "value_score": 75,
            "quality_score": 75,
            "sentiment_score": 75,
            "risk_score": 75,
        },
    ]
    ranked = agent.rank(rows, data_as_of="2026-08-31T23:00:00Z")
    assert [row["symbol"] for row in ranked] == ["AAPL", "MSFT"]
    assert ranked[0]["rank"] == 1
    assert ranked[0]["grade"] == "A"


def test_weights_must_sum_to_one():
    with pytest.raises(ValueError):
        StockRecommendationAgent({"fundamental_score": 0.5})
