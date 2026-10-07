from __future__ import annotations

import json
from pathlib import Path

from paper_live.data_lake import GoogleDriveStorageAgent, LocalDriveMirror
from paper_live.recommendation_cli import main


def _seed(storage: GoogleDriveStorageAgent, tmp_path: Path, *, include_missing: bool = False) -> None:
    rows = []
    for day in ("2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-05", "2026-09-06"):
        row = {
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
        }
        if include_missing and day == "2026-09-06":
            row.pop("available_at")
        rows.append(row)
    storage.write_partitioned_jsonl(
        "market/daily-prices",
        {row["trade_date"]: [row] for row in rows},
        as_of="2026-09-06T23:00:00+00:00",
    )


def test_recommendation_cli_reads_stored_partitions(tmp_path: Path, monkeypatch, capsys):
    storage = GoogleDriveStorageAgent(LocalDriveMirror(tmp_path))
    _seed(storage, tmp_path)
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
    assert payload["quality"]["gate_passed"] is True
    assert payload["recommendation_manifest"]["dataset"] == "recommendations/daily"


def test_recommendation_cli_quality_gate_rejects_missing_timestamp(tmp_path: Path, monkeypatch, capsys):
    storage = GoogleDriveStorageAgent(LocalDriveMirror(tmp_path))
    _seed(storage, tmp_path, include_missing=True)
    monkeypatch.setattr(
        "sys.argv",
        ["paper-live-recommend", "--storage", "local", "--local-dir", str(tmp_path),
         "--dataset", "market/daily-prices", "--decision-time", "2026-09-06T23:30:00+00:00"],
    )
    assert main() == 2
    payload = json.loads(capsys.readouterr().out.split("recommendation quality gate failed:", 1)[0])
    assert payload["quality"]["pit_missing_timestamp"] == 1
    assert payload["quality"]["gate_passed"] is False
