from __future__ import annotations
from dataclasses import dataclass
from .lifecycle import PluginLifecycle, PluginRecord, PluginState

class PluginRollbackError(RuntimeError):
    pass

@dataclass(frozen=True)
class PluginVersion:
    version: str
    commit: str
    artifact_sha256: str

class PluginRollbackManager:
    def __init__(self, lifecycle: PluginLifecycle):
        self.lifecycle = lifecycle
        self._versions: dict[str, list[PluginVersion]] = {}

    def record(self, plugin_id: str, version: PluginVersion) -> None:
        versions = self._versions.setdefault(plugin_id, [])
        if versions and versions[-1] == version:
            return
        versions.append(version)

    def previous(self, plugin_id: str) -> PluginVersion:
        versions = self._versions.get(plugin_id, [])
        if len(versions) < 2:
            raise PluginRollbackError("no previous verified version")
        return versions[-2]

    def rollback(self, plugin_id: str) -> PluginRecord:
        target = self.previous(plugin_id)
        current = self.lifecycle.get(plugin_id)
        self.lifecycle.disable(plugin_id)
        replacement = PluginRecord(plugin_id, target.version, target.commit, target.artifact_sha256, PluginState.VERIFIED)
        self.lifecycle._records[plugin_id] = replacement  # controlled internal transition
        return replacement
