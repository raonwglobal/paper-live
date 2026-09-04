from __future__ import annotations

from dataclasses import dataclass

from .manifest import PluginManifest


@dataclass(frozen=True)
class RegisteredPlugin:
    manifest: PluginManifest
    repository_url: str
    trusted: bool = False
    enabled: bool = False


class PluginRegistry:
    def __init__(self):
        self._plugins: dict[str, RegisteredPlugin] = {}

    def add(self, repository_url: str, manifest: PluginManifest) -> RegisteredPlugin:
        if not repository_url.startswith("https://github.com/"):
            raise ValueError("only HTTPS GitHub repositories are supported")
        manifest.validate()
        plugin = RegisteredPlugin(manifest, repository_url.rstrip("/"))
        self._plugins[manifest.id] = plugin
        return plugin

    def enable(self, plugin_id: str) -> RegisteredPlugin:
        plugin = self._get(plugin_id)
        if not plugin.trusted:
            raise PermissionError("plugin must be verified before enable")
        updated = RegisteredPlugin(plugin.manifest, plugin.repository_url, plugin.trusted, True)
        self._plugins[plugin_id] = updated
        return updated

    def verify(self, plugin_id: str, commit: str, sha256: str) -> RegisteredPlugin:
        plugin = self._get(plugin_id)
        if not commit or not sha256:
            raise ValueError("immutable commit and artifact hash are required")
        manifest = plugin.manifest
        if manifest.source_commit and manifest.source_commit != commit:
            raise ValueError("commit does not match manifest")
        if manifest.sha256 and manifest.sha256 != sha256:
            raise ValueError("artifact hash does not match manifest")
        updated = RegisteredPlugin(manifest, plugin.repository_url, True, False)
        self._plugins[plugin_id] = updated
        return updated

    def get(self, plugin_id: str) -> RegisteredPlugin | None:
        return self._plugins.get(plugin_id)

    def _get(self, plugin_id: str) -> RegisteredPlugin:
        plugin = self.get(plugin_id)
        if plugin is None:
            raise KeyError(plugin_id)
        return plugin
