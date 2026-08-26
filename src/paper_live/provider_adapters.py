from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from .data_skills import DataSkillError, fetch_json

@dataclass(frozen=True)
class ProviderConfig:
    base_url: str
    api_key: str = ""
    timeout: int = 10

class JsonProviderAdapter:
    def __init__(self, config: ProviderConfig):
        if not config.base_url:
            raise ValueError("base_url is required")
        self.config = config

    def get(self, path: str = "") -> Any:
        url = self.config.base_url.rstrip("/") + "/" + path.lstrip("/")
        headers = {"User-Agent": "paper-live/0.1"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return fetch_json(url, headers=headers, timeout=self.config.timeout)

class DartAdapter(JsonProviderAdapter):
    pass

class SecEdgarAdapter(JsonProviderAdapter):
    pass

class OpenBBAdapter(JsonProviderAdapter):
    pass
