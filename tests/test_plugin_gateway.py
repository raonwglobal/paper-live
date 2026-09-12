import pytest

from paper_live.plugins.executor import PluginSkillExecutor
from paper_live.plugins.gateway import PluginCall, PluginExecutionGateway
from paper_live.plugins.lifecycle import PluginLifecycle, PluginLifecycleError, PluginRecord
from paper_live.plugins.skill_registry import RegisteredSkill, SkillRegistry


def setup():
    life = PluginLifecycle()
    life.add(PluginRecord("demo", "1.0.0", "abcdef1", "hash"))
    life.verify("demo")
    life.enable("demo")
    registry = SkillRegistry()
    registry.register(RegisteredSkill("quote", "demo", "1.0.0", "src/main.py"))
    executor = PluginSkillExecutor(registry)
    executor.bind("quote", lambda symbol: {"symbol": symbol})
    return PluginExecutionGateway(life, executor)


def test_integrated_paper_execution():
    gateway = setup()
    result = gateway.execute(PluginCall("demo", "quote", "PAPER_SANDBOX"), symbol="005930")
    assert result == {"symbol": "005930"}


def test_disabled_plugin_is_blocked():
    gateway = setup()
    gateway.lifecycle.disable("demo")
    with pytest.raises(PluginLifecycleError):
        gateway.execute(PluginCall("demo", "quote", "PAPER_SANDBOX"))


def test_live_is_blocked_at_gateway():
    gateway = setup()
    with pytest.raises(PermissionError):
        gateway.execute(PluginCall("demo", "quote", "REAL_LIVE"))


def test_cross_plugin_skill_is_blocked():
    gateway = setup()
    gateway.executor.registry.unregister_plugin("demo")
    with pytest.raises(Exception):
        gateway.execute(PluginCall("demo", "quote", "PAPER_SANDBOX"))
