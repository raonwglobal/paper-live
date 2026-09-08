from paper_live.data_lake import GoogleDriveStorageAgent, LocalDriveMirror
from paper_live.recommendation import StockRecommendationAgent
from paper_live.recommendation_pipeline import RecommendationPipeline

def test_pipeline_ranks_and_persists(tmp_path):
    storage=GoogleDriveStorageAgent(LocalDriveMirror(tmp_path), folder_id="datasets")
    rows=[{"symbol":"A","available_at":"2026-08-28T18:00:00+09:00","fundamental_score":90,"momentum_score":80,"technical_score":80,"value_score":80,"quality_score":80,"sentiment_score":80,"risk_score":80}]
    ranked,manifest=RecommendationPipeline(StockRecommendationAgent(),storage).run(rows,data_as_of="2026-08-28T19:00:00+09:00")
    assert ranked[0]["rank"]==1 and ranked[0]["grade"]=="A"
    assert manifest.row_count==1
