from paper_live.reflection import EpisodicMemory, Episode

def test_recent_returns_latest_entries(tmp_path):
    memory = EpisodicMemory(str(tmp_path / "memory.jsonl"))
    memory.append(Episode("t1", "AAA", "BUY", "WIN", "1", "ok"))
    memory.append(Episode("t2", "BBB", "SELL", "LOSS", "-1", "review"))
    assert [x["symbol"] for x in memory.recent(1)] == ["BBB"]
