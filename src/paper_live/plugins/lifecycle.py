from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from threading import RLock

class PluginState(str, Enum):
    INSTALLED = "installed"
    VERIFIED = "verified"
    ENABLED = "enabled"
    DISABLED = "disabled"
    REMOVED = "removed"

class PluginLifecycleError(RuntimeError):
    pass

@dataclass
class PluginRecord:
    plugin_id: str
    version: str
    commit: str
    artifact_sha256: str
    state: PluginState = PluginState.INSTALLED

class PluginLifecycle:
    def __init__(self):
        self._records: dict[str, PluginRecord] = {}
        self._lock = RLock()

    def add(self, record: PluginRecord) -> None:
        with self._lock:
            if record.plugin_id in self._records and self._records[record.plugin_id].state != PluginState.REMOVED:
                raise PluginLifecycleError("plugin already installed")
            self._records[record.plugin_id] = record

    def verify(self, plugin_id: str) -> PluginRecord:
        with self._lock:
            r = self._get(plugin_id)
            r.state = PluginState.VERIFIED
            return r

    def enable(self, plugin_id: str) -> PluginRecord:
        with self._lock:
            r = self._get(plugin_id)
            if r.state != PluginState.VERIFIED:
                raise PluginLifecycleError("plugin must be verified before enabling")
            r.state = PluginState.ENABLED
            return r

    def disable(self, plugin_id: str) -> PluginRecord:
        with self._lock:
            r = self._get(plugin_id)
            r.state = PluginState.DISABLED
            return r

    def remove(self, plugin_id: str) -> PluginRecord:
        with self._lock:
            r = self._get(plugin_id)
            r.state = PluginState.REMOVED
            return r

    def get(self, plugin_id: str) -> PluginRecord:
        with self._lock:
            return self._get(plugin_id)

    def _get(self, plugin_id: str) -> PluginRecord:
        try:
            r = self._records[plugin_id]
        except KeyError as exc:
            raise PluginLifecycleError(f"unknown plugin: {plugin_id}") from exc
        if r.state == PluginState.REMOVED:
            raise PluginLifecycleError("plugin is removed")
        return r
