from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from threading import RLock

@dataclass(frozen=True)
class PluginAuditEvent:
    action: str
    plugin_id: str
    skill_id: str | None
    mode: str | None
    success: bool
    detail: str = ""
    timestamp: str = ""

    def to_json(self) -> str:
        value = asdict(self)
        if not value["timestamp"]:
            value["timestamp"] = datetime.now(timezone.utc).isoformat()
        return json.dumps(value, sort_keys=True, separators=(",", ":"))

class PluginAuditLog:
    def __init__(self):
        self._events: list[PluginAuditEvent] = []
        self._lock = RLock()

    def append(self, event: PluginAuditEvent) -> None:
        with self._lock:
            self._events.append(event)

    def events(self) -> tuple[PluginAuditEvent, ...]:
        with self._lock:
            return tuple(self._events)
