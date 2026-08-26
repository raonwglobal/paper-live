import pytest
from paper_live.data_skills import DataSkillError, MacroDataSkill, NewsItem, NewsSentimentSkill

def test_news_sentiment_is_deterministic():
    skill = NewsSentimentSkill()
    item = NewsItem("Strong profit growth", "record upgrade")
    assert skill.classify(item) == "POSITIVE"
    assert skill.score(item) == 1.0

def test_macro_skill_rejects_non_object(monkeypatch):
    monkeypatch.setattr("paper_live.data_skills.fetch_json", lambda url: [1, 2, 3])
    with pytest.raises(DataSkillError):
        MacroDataSkill().fetch("https://example.invalid/macro")

def test_macro_skill_normalizes_numeric_values(monkeypatch):
    monkeypatch.setattr("paper_live.data_skills.fetch_json", lambda url: {"vix": 18, "rate": 3.5, "label": "ignored"})
    assert MacroDataSkill().fetch("https://example.invalid/macro").values == {"vix": 18.0, "rate": 3.5}
