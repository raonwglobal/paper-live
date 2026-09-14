from paper_live.recommendation import StockRecommendationAgent


def row(available_at):
    return {
        "symbol": "005930", "available_at": available_at, "fundamental_score": 80,
        "momentum_score": 70, "technical_score": 70, "value_score": 60,
        "quality_score": 70, "sentiment_score": 70, "risk_score": 60,
    }


def test_timezone_aware_pit_guard():
    agent = StockRecommendationAgent()
    assert agent.score(row("2026-08-28T18:00:00+09:00"), data_as_of="2026-08-28T09:30:00Z") is not None
    assert agent.score(row("2026-08-28T20:00:00+09:00"), data_as_of="2026-08-28T09:30:00Z") is None


def test_invalid_timestamp_is_rejected():
    assert StockRecommendationAgent().score(row("not-a-time"), data_as_of="2026-08-28T09:30:00Z") is None
