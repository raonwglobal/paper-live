from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from urllib.request import Request, urlopen


class DataSkillError(RuntimeError):
    pass


def fetch_json(url: str, headers: dict[str, str] | None = None, timeout: int = 10) -> Any:
    request = Request(url, headers=headers or {"User-Agent": "paper-live/0.1"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise DataSkillError(f"data request failed: {url}") from exc


@dataclass(frozen=True)
class MacroSnapshot:
    values: dict[str, float]


class MacroDataSkill:
    def fetch(self, url: str) -> MacroSnapshot:
        payload = fetch_json(url)
        if not isinstance(payload, dict):
            raise DataSkillError("macro response must be an object")
        values = {str(k): float(v) for k, v in payload.items() if isinstance(v, (int, float))}
        return MacroSnapshot(values)


@dataclass(frozen=True)
class NewsItem:
    title: str
    text: str = ""
    url: str = ""


class NewsSentimentSkill:
    POSITIVE = {"beat", "growth", "upgrade", "surge", "profit", "record", "strong", "bullish"}
    NEGATIVE = {"miss", "loss", "downgrade", "crash", "fraud", "weak", "bearish", "decline"}

    def score(self, item: NewsItem) -> float:
        words = {w.strip('.,:;!?()[]{}"').lower() for w in (item.title + " " + item.text).split()}
        pos = len(words & self.POSITIVE)
        neg = len(words & self.NEGATIVE)
        total = pos + neg
        return 0.0 if total == 0 else (pos - neg) / total

    def classify(self, item: NewsItem) -> str:
        value = self.score(item)
        return "POSITIVE" if value > 0.2 else "NEGATIVE" if value < -0.2 else "NEUTRAL"

    def extract(self, items: Sequence[NewsItem]) -> list[dict[str, Any]]:
        return [
            {"title": item.title, "score": self.score(item), "label": self.classify(item), "url": item.url}
            for item in items
        ]
