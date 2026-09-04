from paper_live.data_skills import NewsItem, NewsSentimentSkill
from paper_live.filings import FilingParser, FinancialRAG
from paper_live.vision import ChartAnalysis, ChartVLMSkill


def test_news_sentiment():
    skill = NewsSentimentSkill()
    assert skill.classify(NewsItem("profit growth and upgrade")) == "POSITIVE"
    assert skill.classify(NewsItem("loss downgrade and decline")) == "NEGATIVE"


def test_filing_rag():
    doc = FilingParser().parse("1", "ABC", "DART", "revenue growth profit margin")
    rag = FinancialRAG([doc])
    assert rag.search("revenue growth") == [doc]


def test_chart_vlm_injection():
    class Provider:
        def analyze(self, image_bytes, prompt):
            return ChartAnalysis("UP", 100.0, 120.0, 0.8, "trend")

    result = ChartVLMSkill(Provider()).analyze(b"image")
    assert result.trend == "UP"
