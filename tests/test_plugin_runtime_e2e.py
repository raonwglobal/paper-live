from decimal import Decimal
from paper_live.environment import EnvironmentController, ExecutionEnvironmentMode
from paper_live.execution import ExecutionGateway, OrderRequest, OrderSide, PaperAccount, VirtualMatchingEngine
from paper_live.order_lifecycle import OrderLifecycle
from paper_live.plugins.executor import PluginSkillExecutor
from paper_live.plugins.integration import PluginExecutionRequest, PluginRuntime
from paper_live.plugins.lifecycle import PluginLifecycle, PluginRecord
from paper_live.plugins.risk import *  # noqa: F401,F403
from paper_live.plugins.skill_registry import RegisteredSkill, SkillRegistry
from paper_live.risk import RiskGuardian


def build():
    env = EnvironmentController()
    account = PaperAccount(Decimal("1000000"))
    engine = VirtualMatchingEngine(account)
    execution = ExecutionGateway(env, engine, OrderLifecycle())
    risk = RiskGuardian(env, account)
    lifecycle = PluginLifecycle(); lifecycle.add(PluginRecord("demo", "1.0.0", "abcdef1", "hash")); lifecycle.verify("demo"); lifecycle.enable("demo")
    registry = SkillRegistry(); registry.register(RegisteredSkill("signal.quote", "demo", "1.0.0", "skills/quote.py"))
    executor = PluginSkillExecutor(registry); executor.bind("signal.quote", lambda symbol: {"symbol": symbol, "side": "BUY"})
    return env, account, PluginRuntime(lifecycle, registry, executor, env, risk, execution)


def test_plugin_signal_reaches_paper_only_through_risk_and_gateway():
    env, account, runtime = build()
    request = PluginExecutionRequest("demo", "signal.quote", ExecutionEnvironmentMode.PAPER_SANDBOX)
    assert runtime.invoke(request, symbol="005930")["side"] == "BUY"
    order = OrderRequest("005930", OrderSide.BUY, Decimal("10"), client_order_id="plugin-e2e-1")
    fill = runtime.submit_paper_order(request, order, Decimal("1000"))
    assert fill.quantity == Decimal("10")
    assert account.positions["005930"] == Decimal("10")


def test_plugin_live_is_rejected_before_execution():
    env, account, runtime = build()
    request = PluginExecutionRequest("demo", "signal.quote", ExecutionEnvironmentMode.REAL_LIVE)
    try:
        runtime.invoke(request)
    except PermissionError:
        pass
    else:
        raise AssertionError("REAL_LIVE plugin execution must be rejected")
