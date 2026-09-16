from datetime import date

import pytest

from paper_live.data_lake import GoogleDriveStorageAgent, LocalDriveMirror
from paper_live.market_dataset import DailyDatasetBuilder, DailyPriceIngestionService, DailyPriceNormalizer


class FakeProvider:
    def fetch_daily_prices(self, symbol, start_date, end_date):
        return [
            {
                "code": symbol,
                "date": "20260828",
                "open": "100",
                "high": "110",
                "low": "95",
                "close": "105",
                "volume": "1000",
            },
            {
                "code": symbol,
                "date": "20260828",
                "open": "100",
                "high": "110",
                "low": "95",
                "close": "105",
                "volume": "1000",
            },
        ]


def test_normalizer_supports_broker_style_fields():
    row = DailyPriceNormalizer.normalize(
        {"code": "005930", "stck_bsop_date": "20260828", "stck_clpr": "70000", "acml_vol": "123"},
        symbol="005930",
        market="krx",
        source="kb",
        available_at="2026-08-28T18:00:00+09:00",
    )
    assert row.trade_date == "2026-08-28"
    assert row.close == 70000.0
    assert row.market == "KRX"


def test_ingestion_deduplicates_symbol_date_and_writes_dataset(tmp_path):
    storage = GoogleDriveStorageAgent(LocalDriveMirror(tmp_path), folder_id="datasets")
    service = DailyPriceIngestionService(FakeProvider(), DailyDatasetBuilder(storage))
    manifest = service.collect(
        ["005930", "005930"],
        start_date=date(2026, 8, 28),
        end_date=date(2026, 8, 28),
        market="KRX",
        source="fake",
        available_at="2026-08-28T18:00:00+09:00",
        run_id="run-1",
    )
    assert manifest.row_count == 1
    assert manifest.schema_version == "daily-price-v2"
    assert manifest.source == "fake"
    assert manifest.run_id == "run-1"
    assert manifest.partition_count == 1
    assert manifest.partition_keys == ("2026-08-28",)
    assert (tmp_path / "datasets" / "market" / "daily_prices" / "trade_date=2026-08-28" / "daily_prices.jsonl").exists()


def test_ingestion_rejects_reversed_date_range(tmp_path):
    storage = GoogleDriveStorageAgent(LocalDriveMirror(tmp_path), folder_id="datasets")
    service = DailyPriceIngestionService(FakeProvider(), DailyDatasetBuilder(storage))
    with pytest.raises(ValueError, match="start_date"):
        service.collect(
            ["005930"],
            start_date=date(2026, 8, 29),
            end_date=date(2026, 8, 28),
            market="KRX",
            source="fake",
        )
