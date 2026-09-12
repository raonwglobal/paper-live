import json
from decimal import Decimal

import pytest

from paper_live.brokers.credentials import CredentialParseError, parse_kb_credentials, parse_toss_credentials
from paper_live.brokers.kb import KbCredentials
from paper_live.brokers.protocol import BrokerOrderRequest, OrderResult
from paper_live.brokers.safe_router import BrokerRouter
from paper_live.brokers.toss import TossBrokerAdapter, TossCredentials
from paper_live.environment import EnvironmentController, ExecutionEnvironmentMode
from paper_live.execution import ExecutionGateway, PaperAccount, VirtualMatchingEngine
from paper_live.live_approval import LiveApprovalGate as EnvGate
from paper_live.risk import RiskGuardian
from paper_live.secrets import InMemorySecretStore, SecretBroker, SecretPolicy
from paper_live.security.live_approval_gate import LiveApprovalGate
from paper_live.trade_facade import InternalTradeFacade, OrderIntent


def test_parse_toss_json_and_legacy():
    creds = parse_toss_credentials(json.dumps({"client_id": "a", "client_secret": "b", "account_seq": "1"}))
    assert creds == TossCredentials("a", "b", "1")
    legacy = parse_toss_credentials("cid:csec:99")
    assert legacy.account_seq == "99"
    with pytest.raises(CredentialParseError):
        parse_toss_credentials("bad")


def test_parse_kb_json():
    creds = parse_kb_credentials(json.dumps({"app_key": "k", "app_secret": "s"}))
    assert creds == KbCredentials("k", "s", "/api/v1/ssam1802")


def test_toss_apply_and_clear_restores_base():
    base = TossCredentials("base", "base-sec", "0")
    adapter = TossBrokerAdapter(base)
    material = json.dumps({"client_id": "live", "client_secret": "live-sec", "account_seq": "7"})
    adapter.apply_secret_material(material)
    assert adapter.credentials.client_id == "live"
    assert adapter._ephemeral is True
    adapter.clear_secret_material()
    assert adapter.credentials == base
    assert adapter._ephemeral is False


class RecordingToss(TossBrokerAdapter):
    def __init__(self):
        super().__init__(None)
        self.seen: list[TossCredentials | None] = []
        self.requests: list[BrokerOrderRequest] = []

    def submit(self, request_or_symbol, side=None, quantity=None, price=None):  # type: ignore[override]
        self.seen.append(self.credentials)
        if isinstance(request_or_symbol, BrokerOrderRequest):
            self.requests.append(request_or_symbol)
        return OrderResult("toss", "oid-1", True, "ok")


def test_facade_injects_credentials_before_live_submit_and_clears():
    import hashlib
    import hmac

    secret = "env-secret"
    token = hmac.new(secret.encode(), b"environment-transition", hashlib.sha256).hexdigest()
    env_gate = EnvGate()
    env_gate.approve("operator", "promote")
    controller = EnvironmentController(transition_secret=secret, live_approval_gate=env_gate)
    account = PaperAccount(Decimal("1000000"))
    gateway = ExecutionGateway(controller, VirtualMatchingEngine(account, slippage_bps=Decimal("0")))
    risk = RiskGuardian(controller, account)
    order_gate = LiveApprovalGate()
    recording = RecordingToss()
    router = BrokerRouter({"toss": recording}, approval_gate=order_gate)
    material = json.dumps({"client_id": "c", "client_secret": "s", "account_seq": "1"})
    store = InMemorySecretStore({"toss-order": material})
    secret_broker = SecretBroker(store, SecretPolicy(live_secret_ids=frozenset({"toss-order"})))
    facade = InternalTradeFacade(controller, risk, gateway, router, order_gate, secret_broker)
    controller.set_mode(ExecutionEnvironmentMode.REAL_LIVE, token)

    intent = OrderIntent("005930", "BUY", Decimal("1"), broker="toss")
    approval = order_gate.approve("operator", order_gate.nonce)
    result = facade.submit(intent, Decimal("70000"), approval_id=approval.approval_id)
    assert result.accepted is True
    assert len(recording.seen) == 1
    assert recording.seen[0] is not None
    assert recording.seen[0].client_id == "c"
    # cleared after submit
    assert recording.credentials is None
    assert recording._ephemeral is False
    assert recording.requests[0].side == "BUY"
