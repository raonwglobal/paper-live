from __future__ import annotations
from pathlib import Path
import yaml
from .installer import PluginInstaller, InstalledPlugin
from .lifecycle import PluginLifecycle, PluginRecord
from .loader import RepositorySource
from .manifest import load_manifest
from .security import PluginSecurityValidator
from .skill_registry import SkillRegistry, RegisteredSkill

class PluginManager:
    """Coordinates install -> verify -> registry registration -> enable."""
    def __init__(self, registry: SkillRegistry | None = None, validator: PluginSecurityValidator | None = None,
                 lifecycle: PluginLifecycle | None = None, installer: PluginInstaller | None = None):
        self.registry = registry or SkillRegistry()
        self.validator = validator or PluginSecurityValidator()
        self.lifecycle = lifecycle or PluginLifecycle()
        self.installer = installer or PluginInstaller(validator=self.validator)

    def register_verified(self, manifest):
        manifest.validate()
        self.validator.validate_manifest(manifest)
        for skill_id in manifest.skills:
            self.registry.register(RegisteredSkill(skill_id, manifest.id, manifest.version, manifest.entrypoint))

    def install_and_enable(self, source: RepositorySource, plugin_id: str, version: str, commit: str) -> InstalledPlugin:
        installed = self.installer.install(source, plugin_id, version, commit)
        manifest_path = Path(installed.path) / "plugin.yaml"
        manifest = load_manifest(yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {})
        self.lifecycle.add(PluginRecord(installed.plugin_id, installed.version, installed.commit, installed.artifact_sha256))
        try:
            self.lifecycle.verify(plugin_id)
            self.register_verified(manifest)
            self.lifecycle.enable(plugin_id)
        except Exception:
            self.registry.unregister_plugin(plugin_id)
            self.lifecycle.remove(plugin_id)
            raise
        return installed

    def disable(self, plugin_id: str) -> None:
        self.lifecycle.disable(plugin_id)
        self.registry.unregister_plugin(plugin_id)
