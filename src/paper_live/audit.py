from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AuditEvent:
    event_type: str
    actor: str
    payload: dict[str, Any]
    timestamp: str


class AuditLogger:
    def __init__(self, path: str | Path = "data/audit.jsonl"):
        self.path = Path(path)

    def record(self, event_type: str, actor: str, **payload: Any) -> AuditEvent:
        event = AuditEvent(event_type, actor, payload, datetime.now(UTC).isoformat())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(event), ensure_ascii=False, sort_keys=True) + "\n")
        return event
