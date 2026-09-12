from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ChartAnalysis:
    trend: str
    support: float | None
    resistance: float | None
    confidence: float
    rationale: str


class VisionProvider(Protocol):
    def analyze(self, image_bytes: bytes, prompt: str) -> ChartAnalysis: ...


class ChartVLMSkill:
    """Multimodal boundary. The concrete VLM is injected by deployment."""

    def __init__(self, provider: VisionProvider):
        self.provider = provider

    def analyze(self, image_bytes: bytes) -> ChartAnalysis:
        if not image_bytes:
            raise ValueError("chart image is empty")
        return self.provider.analyze(
            image_bytes,
            "Analyze this financial chart. Return trend, support, resistance, confidence and concise rationale. Do not place orders.",
        )
