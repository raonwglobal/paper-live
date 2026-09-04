import pytest

from paper_live.plugins.lifecycle import PluginLifecycle, PluginLifecycleError, PluginRecord, PluginState


def record():
    return PluginRecord("demo", "1.0.0", "abcdef1", "hash")


def test_verify_then_enable():
    life = PluginLifecycle()
    life.add(record())
    assert life.verify("demo").state == PluginState.VERIFIED
    assert life.enable("demo").state == PluginState.ENABLED


def test_unverified_plugin_cannot_enable():
    life = PluginLifecycle()
    life.add(record())
    with pytest.raises(PluginLifecycleError):
        life.enable("demo")


def test_disable_and_remove():
    life = PluginLifecycle()
    life.add(record())
    life.verify("demo")
    life.enable("demo")
    assert life.disable("demo").state == PluginState.DISABLED
    assert life.remove("demo").state == PluginState.REMOVED
    with pytest.raises(PluginLifecycleError):
        life.get("demo")
