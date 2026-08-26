from __future__ import annotations
from .manifest import PluginManifest
from .skill_registry import RegisteredSkill, SkillRegistry
from .security import PluginSecurityValidator

class PluginManager:
    def __init__(self, registry: SkillRegistry | None = None, validator: PluginSecurityValidator | None = None):
        self.registry = registry or SkillRegistry()
        self.validator = validator or PluginSecurityValidator()

    def register_verified(self, manifest: PluginManifest) -> None:
        manifest.validate()
        self.validator.validate_manifest(manifest)
        for skill_id in manifest.skills:
            self.registry.register(RegisteredSkill(skill_id, manifest.id, manifest.version, manifest.entrypoint))

    def disable(self, plugin_id: str) -> None:
        self.registry.unregister_plugin(plugin_id)
