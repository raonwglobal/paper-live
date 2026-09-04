import pytest

from paper_live.plugins.executor import PluginSkillExecutor, SkillExecutionError
from paper_live.plugins.skill_registry import RegisteredSkill, SkillRegistry


def setup():
    r = SkillRegistry()
    r.register(RegisteredSkill("quote", "demo", "1.0", "src/main.py"))
    return PluginSkillExecutor(r)


def test_bound_skill_executes_in_paper():
    e = setup()
    e.bind("quote", lambda symbol: {"symbol": symbol})
    assert e.execute("quote", mode="PAPER_SANDBOX", symbol="005930")["symbol"] == "005930"


def test_unbound_skill_is_rejected():
    e = setup()
    with pytest.raises(SkillExecutionError):
        e.execute("quote", mode="PAPER_SANDBOX")


def test_plugin_cannot_execute_live():
    e = setup()
    e.bind("quote", lambda: True)
    with pytest.raises(SkillExecutionError):
        e.execute("quote", mode="REAL_LIVE")
