from paper_live.data_lake import GoogleDriveStorageAgent, LocalDriveMirror
from paper_live.recommendation import StockRecommendationAgent
from paper_live.recommendation_pipeline import RecommendationPipeline


def test_pipeline_ranks_and_persists(tmp_path):
    storage = GoogleDriveStorageAgent(LocalDriveMirror(tmp_path), folder_id="datasets")
    rows = [{
        "symbol": "A", "available_at": "2026-08-28T18:00:00+09:00",
        "fundamental_score": 90, "momentum_score": 80, "technical_score": 80,
        "value_score": 80, "quality_score": 80, "sentiment_score": 80, "risk_score": 80,
    }]
    ranked, manifest = RecommendationPipeline(StockRecommendationAgent(), storage).run(
        rows, data_as_of="2026-08-28T19:00:00+09:00"
    )
    assert ranked[0]["rank"] == 1 and ranked[0]["grade"] == "A"
    assert manifest.row_count == 1


def test_build_from_daily_uses_latest_pit_row_per_symbol(tmp_path):
    storage = GoogleDriveStorageAgent(LocalDriveMirror(tmp_path), folder_id="datasets")
    pipeline = RecommendationPipeline(storage=storage)
    rows = [
        {"market": "KRX", "symbol": "A", "trade_date": "2026-08-27", "close": 100, "volume": 100,
         "available_at": "2026-08-27T18:00:00+09:00"},
        {"market": "KRX", "symbol": "A", "trade_date": "2026-08-28", "close": 110, "volume": 120,
         "available_at": "2026-08-28T18:00:00+09:00"},
        {"market": "KRX", "symbol": "A", "trade_date": "2026-08-29", "close": 130, "volume": 150,
         "available_at": "2026-08-29T18:00:00+09:00"},
        {"market": "KRX", "symbol": "B", "trade_date": "2026-08-27", "close": 80, "volume": 70,
         "available_at": "2026-08-27T18:00:00+09:00"},
        {"market": "KRX", "symbol": "B", "trade_date": "2026-08-28", "close": 90, "volume": 80,
         "available_at": "2026-08-28T18:30:00+09:00"},
    ]
    ranked, feature_manifest, recommendation_manifest = pipeline.build_from_daily(
        rows, decision_time="2026-08-28T19:00:00+09:00"
    )
    assert feature_manifest.row_count == 4
    assert recommendation_manifest.row_count == 2
    assert {item["symbol"] for item in ranked} == {"A", "B"}
    assert {item["trade_date"] for item in ranked} == {"2026-08-28"}
    assert all(item["input_checksum_sha256"] for item in ranked)


def test_quality_filters_remove_insufficient_and_invalid_candidates(tmp_path):
    storage = GoogleDriveStorageAgent(LocalDriveMirror(tmp_path), folder_id="datasets")
    pipeline = RecommendationPipeline(storage=storage, min_history=2, max_abs_return_1d=0.20)
    rows = [
        {"market": "KRX", "symbol": "GOOD", "trade_date": "2026-08-27", "open": 99, "high": 101, "low": 98, "close": 100, "volume": 100,
         "available_at": "2026-08-27T18:00:00+09:00"},
        {"market": "KRX", "symbol": "GOOD", "trade_date": "2026-08-28", "open": 109, "high": 111, "low": 108, "close": 110, "volume": 120,
         "available_at": "2026-08-28T18:00:00+09:00"},
        {"market": "KRX", "symbol": "SHORT", "trade_date": "2026-08-28", "close": 90, "volume": 100,
         "available_at": "2026-08-28T18:00:00+09:00"},
        {"market": "KRX", "symbol": "ZERO", "trade_date": "2026-08-27", "close": 100, "volume": 0,
         "available_at": "2026-08-27T18:00:00+09:00"},
        {"market": "KRX", "symbol": "ZERO", "trade_date": "2026-08-28", "close": 100, "volume": 0,
         "available_at": "2026-08-28T18:00:00+09:00"},
        {"market": "KRX", "symbol": "JUMP", "trade_date": "2026-08-27", "close": 100, "volume": 100,
         "available_at": "2026-08-27T18:00:00+09:00"},
        {"market": "KRX", "symbol": "JUMP", "trade_date": "2026-08-28", "close": 140, "volume": 100,
         "available_at": "2026-08-28T18:00:00+09:00"},
    ]
    ranked, _, _ = pipeline.build_from_daily(rows, decision_time="2026-08-28T19:00:00+09:00")
    assert [row["symbol"] for row in ranked] == ["GOOD"]
    assert pipeline.last_filter_stats["filtered_history"] == 1
    assert pipeline.last_filter_stats["filtered_volume"] == 1
    assert pipeline.last_filter_stats["filtered_return"] == 1
    assert pipeline.last_filter_stats["selected_candidates"] == 1


def test_factor_scores_preserve_normalized_daily_ranges(tmp_path):
    storage = GoogleDriveStorageAgent(LocalDriveMirror(tmp_path), folder_id="datasets")
    pipeline = RecommendationPipeline(storage=storage)
    factors = pipeline._factorize({"momentum": 0.10, "return_1d": 0.02, "volatility": 0.05})
    assert factors["momentum_score"] == 55.0
    assert factors["technical_score"] == 51.0
    assert factors["risk_score"] == 47.5
