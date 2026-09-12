from datetime import date

from paper_live.broker_market_data import TossCredentials, TossDailyPriceProvider, TossTokenProvider


def test_toss_token_provider_posts_client_credentials(monkeypatch):
    calls = []

    def fake(url, **kwargs):
        calls.append((url, kwargs))
        return {"access_token": "token"}

    monkeypatch.setattr("paper_live.broker_market_data._json_request", fake)
    token = TossTokenProvider(TossCredentials("id", "secret")).token()
    assert token == "token"
    assert calls[0][0].endswith("/oauth2/token")


def test_toss_daily_provider_normalizes_paginated_candles(monkeypatch):
    responses = iter(
        [
            {
                "result": {
                    "candles": [
                        {
                            "timestamp": "2026-08-28T09:00:00+09:00",
                            "openPrice": "100",
                            "highPrice": "110",
                            "lowPrice": "90",
                            "closePrice": "105",
                            "volume": "1000",
                            "currency": "KRW",
                        }
                    ],
                    "nextBefore": None,
                }
            }
        ]
    )
    monkeypatch.setattr(TossDailyPriceProvider, "_get", lambda self, path, params: next(responses))
    p = TossDailyPriceProvider(TossCredentials("id", "secret"))
    rows = p.fetch_daily_prices("005930", date(2026, 8, 28), date(2026, 8, 28))
    assert rows[0]["close"] == "105"
