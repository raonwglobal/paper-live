from __future__ import annotations

import pytest

from paper_live.deployment_config import build_google_drive_storage, load_security_master_csv


def test_load_security_master_csv_normalizes_and_filters(tmp_path):
    path = tmp_path / "universe.csv"
    path.write_text(
        "symbol,name,market,currency,active\n005930,Samsung,KOSPI,KRW,true\n"
        "AAPL,Apple,nasdaq,usd,false\n",
        encoding="utf-8",
    )
    universe = load_security_master_csv(path)
    assert [(item.symbol, item.market) for item in universe.active()] == [("005930", "KOSPI")]
    assert universe.active()[0].currency == "KRW"


def test_load_security_master_csv_rejects_missing_columns(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("symbol,name\nABC,Example\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing required columns"):
        load_security_master_csv(path)


def test_load_security_master_csv_rejects_invalid_active(tmp_path):
    path = tmp_path / "bad-active.csv"
    path.write_text("symbol,name,market,active\nABC,Example,NYSE,maybe\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid active"):
        load_security_master_csv(path)


def test_build_google_drive_storage_requires_token(monkeypatch):
    monkeypatch.delenv("GOOGLE_DRIVE_DATA_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("GOOGLE_DRIVE_ACCESS_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="token is missing"):
        build_google_drive_storage()
