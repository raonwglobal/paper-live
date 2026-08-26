from decimal import Decimal
import pytest

from paper_live import EnvironmentController, ExecutionEnvironmentMode, OrderRequest, OrderSide, PaperAccount
from paper_live.agents import AgentState, DebateOrchestratorAgent
from paper_live.live_approval import LiveApprovalGate
from paper_live.risk import RiskGuardian, RiskLimits
from paper_live.skills import Skill, SkillRegistry


def test_risk_rejects_oversized_order():
    c = EnvironmentController()
    r = RiskGuardian(c, PaperAccount(Decimal("100000")), RiskLimits(max_order_notional=Decimal("1000")))
    with pytest.raises(PermissionError):
        r.approve(OrderRequest("ABC", OrderSide.BUY, Decimal("2")), Decimal("1000"))


def test_circuit_breaker_blocks_order():
    c = EnvironmentController()
    r = RiskGuardian(c, PaperAccount(Decimal("100000")))
    r.circuit_breaker.trip()
    with pytest.raises(PermissionError):
        r.approve(OrderRequest("ABC", OrderSide.BUY, Decimal("1")), Decimal("10"))


def test_debate_produces_buy_when_bullish_signals_win():
    state = AgentState("ABC", market={"macro_regime": "BULLISH", "fundamental_signal": "BUY", "technical_signal": "BUY", "sentiment_signal": "NEUTRAL"})
    state = DebateOrchestratorAgent().run(state)
    assert state.decision["action"] == "BUY"


def test_skill_registry_enforces_environment():
    c = EnvironmentController()
    registry = SkillRegistry(c)
    registry.register(Skill("skill-virtual-matching-engine", lambda value: value + 1))
    assert registry.invoke("skill-virtual-matching-engine", value=1) == 2
    registry.register(Skill("skill-toss-broker", lambda: "must-not-run"))
    with pytest.raises(Exception):
        registry.invoke("skill-toss-broker")


def test_live_mode_has_broker_allowlist_but_not_paper_gateway():
    secret = "s"
    import hashlib, hmac
    token = hmac.new(secret.encode(), b"environment-transition", hashlib.sha256).hexdigest()
    gate = LiveApprovalGate()
    gate.approve("test-operator", "test allowlist")
    c = EnvironmentController(transition_secret=secret, live_approval_gate=gate)
    c.set_mode(ExecutionEnvironmentMode.REAL_LIVE, token)
    assert c.is_skill_allowed("skill-toss-broker")
    assert not c.is_skill_allowed("skill-virtual-matching-engine")
