from paper_live.market_data_schema import validate_daily_market_schema


def test_daily_market_schema_accepts_valid_pit_fields():
    rows = [{
        "symbol": "AAPL",
        "market": "NASDAQ",
        "trade_date": "2026-09-06",
        "effective_date": "2026-09-06",
        "available_at": "2026-09-06T23:59:59+00:00",
    }]
    assert validate_daily_market_schema(rows) == ()


def test_daily_market_schema_rejects_identity_and_timestamp_shape_errors():
    rows = [{
        "symbol": "",
        "market": "",
        "trade_date": "not-a-date",
        "effective_date": "2026-09-05",
        "available_at": "2026-09-06T23:59:59",
    }]
    errors = validate_daily_market_schema(rows)
    assert any("symbol is required" in error for error in errors)
    assert any("market is required" in error for error in errors)
    assert any("trade_date must be YYYY-MM-DD" in error for error in errors)
    assert any("effective_date must match trade_date" in error for error in errors)
    assert any("available_at must include timezone" in error for error in errors)
