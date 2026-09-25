from paper_live.reflection import EpisodicMemory, TradeEpisode


def test_read_all_returns_all_entries(tmp_path):
    memory = EpisodicMemory(tmp_path / "memory.jsonl")
    memory.append(TradeEpisode("1", "AAA", "BUY", "10", "12", "2", {}, "POSITIVE", "t1"))
    memory.append(TradeEpisode("2", "BBB", "SELL", "10", "9", "-1", {}, "NEGATIVE", "t2"))
    episodes = memory.read_all()
    assert [x.symbol for x in episodes] == ["AAA", "BBB"]


def test_read_all_empty_memory(tmp_path):
    assert EpisodicMemory(tmp_path / "missing.jsonl").read_all() == []
