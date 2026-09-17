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
    assert row.currency == "KRW"


def test_normalizer_supports_explicit_international_currency():
    row = DailyPriceNormalizer.normalize(
        {"ticker": "AAPL", "date": "2026-08-28", "close": "230.50", "currency": "usd"},
        symbol="AAPL",
        market="NASDAQ",
        source="market-api",
        available_at="2026-08-29T01:00:00+00:00",
        currency="EUR",
    )
    assert row.symbol == "AAPL"
    assert row.market == "NASDAQ"
    assert row.currency == "USD"


def test_normalizer_rejects_invalid_currency():
    with pytest.raises(ValueError, match="3-letter ISO"):
        DailyPriceNormalizer.normalize(
            {"code": "AAPL", "date": "2026-08-28", "close": "230", "currency": "US"},
            symbol="AAPL",
            market="NASDAQ",
            source="market-api",
            available_at="2026-08-29T01:00:00+00:00",
        )


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


def test_builder_preserves_multi_source_lineage(tmp_path):
    storage = GoogleDriveStorageAgent(LocalDriveMirror(tmp_path), folder_id="datasets")
    builder = DailyDatasetBuilder(storage)
    from paper_live.market_dataset import DailyPriceRecord

    rows = [
        DailyPriceRecord("005930", "KRX", "2026-08-28", 1, 1, 1, 1, 1, source="kb", available_at="2026-08-28T18:00:00+09:00"),
        DailyPriceRecord("AAPL", "NASDAQ", "2026-08-28", 2, 2, 2, 2, 2, source="toss", currency="USD", available_at="2026-08-29T01:00:00+00:00"),
    ]
    manifest = builder.build(rows, as_of="2026-08-29T02:00:00+00:00")
    assert manifest.source == "multi:kb,toss"
    assert manifest.row_count == 2


def test_ingestion_rejects_invalid_available_at(tmp_path):
    storage = GoogleDriveStorageAgent(LocalDriveMirror(tmp_path), folder_id="datasets")
    service = DailyPriceIngestionService(FakeProvider(), DailyDatasetBuilder(storage))
    with pytest.raises(ValueError, match="ISO-8601"):
        service.collect(
            ["005930"],
            start_date=date(2026, 8, 28),
            end_date=date(2026, 8, 28),
            market="KRX",
            source="fake",
            available_at="not-a-timestamp",
        )


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


def test_partition_writer_rejects_mismatched_row_date(tmp_path):
    storage = GoogleDriveStorageAgent(LocalDriveMirror(tmp_path), folder_id="datasets")
    with pytest.raises(ValueError, match="does not match partition"):
        storage.write_partitioned_jsonl(
            "market/daily_prices",
            {"2026-08-28": [{"market": "KRX", "symbol": "005930", "trade_date": "2026-08-29", "close": 1}]},
            as_of="2026-08-29T00:00:00+00:00",
        )


def test_partition_writer_normalizes_partition_keys(tmp_path):
    storage = GoogleDriveStorageAgent(LocalDriveMirror(tmp_path), folder_id="datasets")
    manifest = storage.write_partitioned_jsonl(
        "market/daily_prices",
        {"20260828": [{"market": "KRX", "symbol": "005930", "trade_date": "2026-08-28", "close": 1}]},
        as_of="2026-08-29T00:00:00+00:00",
    )
    assert manifest.partition_keys == ("2026-08-28",)
