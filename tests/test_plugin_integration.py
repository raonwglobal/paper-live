from decimal import Decimal
import pytest
from paper_live.environment import EnvironmentController, ExecutionEnvironmentMode
from paper_live.execution import ExecutionGateway, OrderRequest, OrderSide, PaperAccount, VirtualMatchingEngine
from paper_live.risk import RiskGuardian
from paper_live.plugins.executor import PluginSkillExecutor
from paper_live.plugins.integration import PluginExecutionRequest, PluginRuntime
from paper_live.plugins.lifecycle import PluginLifecycle, PluginRecord
from paper_live.plugins.skill_registry import RegisteredSkill, SkillRegistry

def runtime():
    env = EnvironmentController()
    account = PaperAccount(Decimal("100000"))
    risk = RiskGuardian(env, account)
    execution = ExecutionGateway(env, VirtualMatchingEngine(account))
    lifecycle = PluginLifecycle(); lifecycle.add(PluginRecord("demo", "1.0", "abcdef1", "hash")); lifecycle.verify("demo"); lifecycle.enable("demo")
    registry = SkillRegistry(); registry.register(RegisteredSkill("signal", "demo", "1.0", "src/main.py"))
    executor = PluginSkillExecutor(registry); executor.bind("signal", lambda: {"signal": "BUY"})
    return PluginRuntime(lifecycle, registry, executor, env, risk, execution)

def test_plugin_invocation_and_paper_order_share_environment():
    rt = runtime()
    request = PluginExecutionRequest("demo", "signal", ExecutionEnvironmentMode.PAPER_SANDBOX)
    assert rt.invoke(request) == {"signal": "BUY"}
    order = OrderRequest("005930", OrderSide.BUY, Decimal("10"), client_order_id="plugin-order-1")
    fill = rt.submit_paper_order(request, order, Decimal("1000"))
    assert fill.quantity == Decimal("10")

def test_plugin_live_order_is_rejected():
    rt = runtime()
    request = PluginExecutionRequest("demo", "signal", ExecutionEnvironmentMode.REAL_LIVE)
    order = OrderRequest("005930", OrderSide.BUY, Decimal("1"), client_order_id="plugin-live-1")
    with pytest.raises(PermissionError): rt.submit_paper_order(request, order, Decimal("1000"))

def test_plugin_mode_mismatch_is_rejected():
    rt = runtime()
    request = PluginExecutionRequest("demo", "signal", ExecutionEnvironmentMode.VIRTUAL_BACKTEST)
    with pytest.raises(PermissionError): rt.invoke(request)
