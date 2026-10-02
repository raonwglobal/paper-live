from datetime import date

from paper_live.data_quality import validate_daily_rows


def test_daily_quality_accepts_valid_rows():
    report = validate_daily_rows(
        [{"symbol": "ABC", "trade_date": "2026-01-02", "open": 10, "high": 12, "low": 9, "close": 11, "volume": 100}],
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
    )
    assert report.passed
    assert report.row_count == 1


def test_daily_quality_detects_duplicate_and_bad_ohlc():
    row = {"symbol": "ABC", "trade_date": "2026-01-02", "open": 13, "high": 12, "low": 9, "close": None}
    report = validate_daily_rows(
        [row, row], start_date=date(2026, 1, 1), end_date=date(2026, 1, 3)
    )
    assert report.duplicate_count == 1
    assert report.missing_close_count == 2
    assert report.invalid_count == 2
    assert not report.passed


def test_daily_quality_detects_date_outside_range():
    report = validate_daily_rows(
        [{"symbol": "ABC", "trade_date": "2025-12-31", "close": 1}],
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
    )
    assert report.date_out_of_range_count == 1
