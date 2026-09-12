import pytest

from paper_live.plugins.manager import PluginManager
from paper_live.plugins.manifest import PluginManifest
from paper_live.plugins.skill_registry import SkillRegistryError


def manifest(pid="demo", skills=("market.quote",)):
    return PluginManifest(pid, "1.0.0", "Demo", "src/main.py", skills=skills)


def test_verified_plugin_registers_skills():
    manager = PluginManager()
    manager.register_verified(manifest())
    assert manager.registry.resolve("market.quote").plugin_id == "demo"


def test_skill_collision_between_plugins_is_rejected():
    manager = PluginManager()
    manager.register_verified(manifest("one"))
    with pytest.raises(SkillRegistryError):
        manager.register_verified(manifest("two"))


def test_disable_unregisters_plugin_skills():
    manager = PluginManager()
    manager.register_verified(manifest())
    manager.disable("demo")
    with pytest.raises(SkillRegistryError):
        manager.registry.resolve("market.quote")
