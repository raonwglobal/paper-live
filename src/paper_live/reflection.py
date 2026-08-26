from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TradeEpisode:
    episode_id: str
    symbol: str
    action: str
    entry_price: str
    exit_price: str
    pnl: str
    decision_context: dict[str, Any]
    outcome: str
    created_at: str


class EpisodicMemory:
    def __init__(self, path: str | Path = "data/episodic_memory.jsonl"):
        self.path = Path(path)

    def append(self, episode: TradeEpisode) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(episode), ensure_ascii=False) + "\n")

    def read_all(self) -> list[TradeEpisode]:
        if not self.path.exists():
            return []
        return [TradeEpisode(**json.loads(line)) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]


class SelfReflectionWorker:
    def __init__(self, memory: EpisodicMemory):
        self.memory = memory

    def reflect(self, episode: TradeEpisode) -> dict[str, Any]:
        pnl = float(episode.pnl)
        verdict = "POSITIVE" if pnl > 0 else "NEGATIVE" if pnl < 0 else "NEUTRAL"
        lesson = "preserve decision context" if pnl > 0 else "review signal and risk gate" if pnl < 0 else "insufficient outcome signal"
        self.memory.append(episode)
        return {"episode_id": episode.episode_id, "verdict": verdict, "lesson": lesson, "reflected_at": datetime.now(timezone.utc).isoformat()}
