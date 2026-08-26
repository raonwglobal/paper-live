from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import re

_PLUGIN_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")

@dataclass(frozen=True)
class PermissionPolicy:
    network_allow: tuple[str, ...] = ()
    secret_allow: tuple[str, ...] = ()
    filesystem_read: tuple[str, ...] = ()
    shell: bool = False
    allowed_modes: tuple[str, ...] = ("PAPER_SANDBOX", "VIRTUAL_BACKTEST")

@dataclass(frozen=True)
class PluginManifest:
    id: str
    version: str
    name: str
    entrypoint: str
    skills: tuple[str, ...] = ()
    permissions: PermissionPolicy = field(default_factory=PermissionPolicy)
    source_commit: str | None = None
    sha256: str | None = None

    def validate(self) -> None:
        if not _PLUGIN_ID.fullmatch(self.id): raise ValueError("invalid plugin id")
        if not self.version.strip() or not self.name.strip(): raise ValueError("version and name are required")
        entry = Path(self.entrypoint)
        if entry.is_absolute() or ".." in entry.parts: raise ValueError("entrypoint must stay inside plugin")
        if self.permissions.shell: raise ValueError("shell execution must be explicitly enabled outside the default policy")
        if "REAL_LIVE" in self.permissions.allowed_modes:
            raise ValueError("REAL_LIVE cannot be granted by a plugin manifest")

def load_manifest(data: dict) -> PluginManifest:
    plugin = data.get("plugin") or {}
    runtime = data.get("runtime") or {}
    raw = data.get("permissions") or {}
    execution = data.get("execution") or {}
    manifest = PluginManifest(
        id=str(plugin.get("id", "")), version=str(plugin.get("version", "")), name=str(plugin.get("name", "")),
        entrypoint=str(runtime.get("entrypoint", "")), skills=tuple(str(x) for x in data.get("skills", [])),
        permissions=PermissionPolicy(
            tuple(raw.get("network", {}).get("allow", [])), tuple(raw.get("secrets", {}).get("allow", [])),
            tuple(raw.get("filesystem", {}).get("read", [])), bool(raw.get("shell", False)),
            tuple(execution.get("allowed_modes", ["PAPER_SANDBOX", "VIRTUAL_BACKTEST"]))),
        source_commit=(data.get("source") or {}).get("commit"), sha256=(data.get("integrity") or {}).get("sha256"))
    manifest.validate()
    return manifest
