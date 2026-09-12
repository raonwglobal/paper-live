from decimal import Decimal

import pytest

from paper_live.brokers.protocol import BrokerOrderRequest, OrderResult
from paper_live.brokers.safe_router import BrokerRouter
from paper_live.environment import EnvironmentController, ExecutionEnvironmentMode
from paper_live.execution import ExecutionGateway, Fill, PaperAccount, VirtualMatchingEngine
from paper_live.risk import RiskGuardian, RiskLimits
from paper_live.secrets import InMemorySecretStore, SecretAccessDenied, SecretBroker, SecretPolicy
from paper_live.security.live_approval_gate import LiveApprovalGate
from paper_live.trade_facade import InternalTradeFacade, OrderIntent


class FakeBroker:
    name = "toss"

    def __init__(self):
        self.last_request: BrokerOrderRequest | None = None
        self.cancelled: list[str] = []

    def submit(self, request: BrokerOrderRequest) -> OrderResult:
        self.last_request = request
        return OrderResult("toss", "ord-1", True, "ok")

    def cancel(self, order_id: str) -> bool:
        self.cancelled.append(order_id)
        return True


def _facade(*, live: bool = False, secrets: dict[str, str] | None = None):
    controller = EnvironmentController()
    account = PaperAccount(Decimal("1000000"))
    engine = VirtualMatchingEngine(account, slippage_bps=Decimal("0"))
    gateway = ExecutionGateway(controller, engine)
    risk = RiskGuardian(controller, account, RiskLimits(max_order_notional=Decimal("500000")))
    order_gate = LiveApprovalGate()
    router = BrokerRouter({"toss": FakeBroker()}, approval_gate=order_gate)
    store = InMemorySecretStore(secrets or {"toss-order": "secret-token-value"})
    policy = SecretPolicy(live_secret_ids=frozenset({"toss-order"}))
    secret_broker = SecretBroker(store, policy)
    facade = InternalTradeFacade(
        controller=controller,
        risk=risk,
        gateway=gateway,
        broker_router=router,
        order_approval_gate=order_gate,
        secret_broker=secret_broker,
    )
    return facade, controller, order_gate, router


def test_preview_paper_path_does_not_require_approval():
    facade, _, _, _ = _facade()
    intent = OrderIntent("005930", "BUY", Decimal("2"), price=Decimal("70000"))
    preview = facade.preview(intent, Decimal("70000"))
    assert preview.risk.approved is True
    assert preview.requires_approval is False
    assert preview.estimated_notional == Decimal("140000")
    assert preview.mode == "PAPER_SANDBOX"


def test_submit_paper_path_returns_fill():
    facade, _, _, _ = _facade()
    intent = OrderIntent("005930", "BUY", Decimal("2"), client_order_id="facade-1")
    result = facade.submit(intent, Decimal("1000"))
    assert isinstance(result, Fill)
    assert result.quantity == Decimal("2")


def test_preview_risk_rejection():
    facade, _, _, _ = _facade()
    intent = OrderIntent("005930", "BUY", Decimal("100"), price=Decimal("10000"))
    # notional 1_000_000 > max 500_000
    preview = facade.preview(intent, Decimal("10000"))
    assert preview.risk.approved is False
    assert preview.risk.level == "REJECT"
    assert preview.risk.violations


def test_live_submit_requires_approval_and_secret(monkeypatch):
    import hashlib
    import hmac

    secret = "env-secret"
    token = hmac.new(secret.encode(), b"environment-transition", hashlib.sha256).hexdigest()
    from paper_live.live_approval import LiveApprovalGate as EnvGate

    env_gate = EnvGate()
    env_gate.approve("operator", "promote")
    controller = EnvironmentController(transition_secret=secret, live_approval_gate=env_gate)
    account = PaperAccount(Decimal("1000000"))
    engine = VirtualMatchingEngine(account, slippage_bps=Decimal("0"))
    gateway = ExecutionGateway(controller, engine)
    risk = RiskGuardian(controller, account)
    order_gate = LiveApprovalGate()
    fake = FakeBroker()
    router = BrokerRouter({"toss": fake}, approval_gate=order_gate)
    store = InMemorySecretStore({"toss-order": "live-token"})
    secret_broker = SecretBroker(store, SecretPolicy(live_secret_ids=frozenset({"toss-order"})))
    facade = InternalTradeFacade(controller, risk, gateway, router, order_gate, secret_broker)
    controller.set_mode(ExecutionEnvironmentMode.REAL_LIVE, token)

    intent = OrderIntent("005930", "BUY", Decimal("1"), broker="toss", client_order_id="live-1")
    preview = facade.preview(intent, Decimal("70000"))
    assert preview.requires_approval is True

    with pytest.raises(PermissionError):
        facade.submit(intent, Decimal("70000"))  # no approval_id

    approval = order_gate.approve("operator", order_gate.nonce)
    result = facade.submit(intent, Decimal("70000"), approval_id=approval.approval_id)
    assert isinstance(result, OrderResult)
    assert result.accepted is True
    assert fake.last_request is not None
    assert fake.last_request.symbol == "005930"


def test_live_submit_denied_without_secret_mapping():
    import hashlib
    import hmac

    secret = "env-secret"
    token = hmac.new(secret.encode(), b"environment-transition", hashlib.sha256).hexdigest()
    from paper_live.live_approval import LiveApprovalGate as EnvGate

    env_gate = EnvGate()
    env_gate.approve("operator", "promote")
    controller = EnvironmentController(transition_secret=secret, live_approval_gate=env_gate)
    account = PaperAccount(Decimal("1000000"))
    gateway = ExecutionGateway(controller, VirtualMatchingEngine(account))
    risk = RiskGuardian(controller, account)
    order_gate = LiveApprovalGate()
    router = BrokerRouter({"toss": FakeBroker()}, approval_gate=order_gate)
    # empty store → KeyError wrapped path via resolve
    secret_broker = SecretBroker(InMemorySecretStore({}), SecretPolicy(live_secret_ids=frozenset({"toss-order"})))
    facade = InternalTradeFacade(controller, risk, gateway, router, order_gate, secret_broker)
    controller.set_mode(ExecutionEnvironmentMode.REAL_LIVE, token)
    intent = OrderIntent("005930", "BUY", Decimal("1"), broker="toss")
    approval = order_gate.approve("operator", order_gate.nonce)
    with pytest.raises(KeyError):
        facade.submit(intent, Decimal("70000"), approval_id=approval.approval_id)


def test_secret_policy_blocks_resolve_in_paper_mode():
    store = InMemorySecretStore({"toss-order": "x"})
    broker = SecretBroker(store, SecretPolicy(live_secret_ids=frozenset({"toss-order"})))
    with pytest.raises(SecretAccessDenied):
        broker.resolve(secret_id="toss-order", mode="PAPER_SANDBOX", capability="order.create")


def test_live_cancel_requires_approval_and_succeeds():
    import hashlib
    import hmac

    secret = "env-secret"
    token = hmac.new(secret.encode(), b"environment-transition", hashlib.sha256).hexdigest()
    from paper_live.live_approval import LiveApprovalGate as EnvGate

    env_gate = EnvGate()
    env_gate.approve("operator", "promote")
    controller = EnvironmentController(transition_secret=secret, live_approval_gate=env_gate)
    account = PaperAccount(Decimal("1000000"))
    gateway = ExecutionGateway(controller, VirtualMatchingEngine(account))
    risk = RiskGuardian(controller, account)
    order_gate = LiveApprovalGate()
    fake = FakeBroker()
    router = BrokerRouter({"toss": fake}, approval_gate=order_gate)
    secret_broker = SecretBroker(
        InMemorySecretStore({"toss-order": "secret-token-value"}),
        SecretPolicy(live_secret_ids=frozenset({"toss-order"})),
    )
    facade = InternalTradeFacade(controller, risk, gateway, router, order_gate, secret_broker)
    controller.set_mode(ExecutionEnvironmentMode.REAL_LIVE, token)

    with pytest.raises(PermissionError):
        facade.cancel(broker="toss", order_id="ord-9")

    approval = order_gate.approve("operator", order_gate.nonce)
    assert facade.cancel(broker="toss", order_id="ord-9", approval_id=approval.approval_id) is True
    assert fake.cancelled == ["ord-9"]


def test_cancel_rejected_outside_real_live():
    facade, _controller, order_gate, _router = _facade()
    approval = order_gate.approve("operator", order_gate.nonce)
    with pytest.raises(PermissionError, match="REAL_LIVE"):
        facade.cancel(broker="toss", order_id="ord-1", approval_id=approval.approval_id)
