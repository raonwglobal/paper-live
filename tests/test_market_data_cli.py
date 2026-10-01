from paper_live.market_data_cli import _load_universe


def test_load_universe_csv_supports_optional_fields(tmp_path):
    path = tmp_path / "universe.csv"
    path.write_text(
        "symbol,name,market,currency,active\n005930,Samsung,KOSPI,KRW,true\n"
        "DELISTED,Old Co,NASDAQ,USD,false\n",
        encoding="utf-8",
    )

    master = _load_universe(str(path))

    assert len(master.active()) == 1
    security = master.active()[0]
    assert (security.symbol, security.name, security.market, security.currency) == (
        "005930", "Samsung", "KOSPI", "KRW"
    )


def test_load_universe_requires_core_columns(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("ticker,name\nABC,Example\n", encoding="utf-8")

    import pytest
    with pytest.raises(ValueError, match="symbol,name,market"):
        _load_universe(str(path))
