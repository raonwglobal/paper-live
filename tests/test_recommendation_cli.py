from __future__ import annotations

import json
from pathlib import Path

from paper_live.data_lake import GoogleDriveStorageAgent, LocalDriveMirror
from paper_live.recommendation_cli import main


def test_recommendation_cli_reads_stored_partitions(tmp_path: Path, monkeypatch, capsys):
    storage = GoogleDriveStorageAgent(LocalDriveMirror(tmp_path))
    rows = []
    for day in ("2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-05", "2026-09-06"):
        rows.append({
            "symbol": "AAPL",
            "market": "NASDAQ",
            "trade_date": day,
            "open": 100,
            "high": 105,
            "low": 95,
            "close": 102,
            "volume": 1000000,
            "value": 100000000,
            "adjusted_close": 102,
            "source": "test",
            "currency": "USD",
            "available_at": f"{day}T23:00:00+00:00",
        })
    storage.write_partitioned_jsonl(
        "market/daily-prices",
        {row["trade_date"]: [row] for row in rows},
        as_of="2026-09-06T23:00:00+00:00",
    )
    monkeypatch.setenv("PAPER_LIVE_TEST_ARGS", "")
    monkeypatch.setattr(
        "sys.argv",
        ["paper-live-recommend", "--storage", "local", "--local-dir", str(tmp_path),
         "--dataset", "market/daily-prices", "--decision-time", "2026-09-06T23:30:00+00:00"],
    )
    assert main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["input_rows"] == 6
    assert payload["quality"]["pit_eligible"] == 6
    assert payload["quality"]["pit_rejected"] == 0
    assert payload["recommendation_manifest"]["dataset"] == "recommendations/daily"
