import json
import urllib.error
import urllib.request
from decimal import Decimal

import pytest

from paper_live.brokers.protocol import BrokerOrderRequest, OrderResult
from paper_live.brokers.safe_router import BrokerRouter
from paper_live.environment import EnvironmentController, ExecutionEnvironmentMode
from paper_live.execution import ExecutionGateway, PaperAccount, VirtualMatchingEngine
from paper_live.internal_api import create_internal_server
from paper_live.risk import RiskGuardian, RiskLimits
from paper_live.secrets import InMemorySecretStore, SecretBroker, SecretPolicy
from paper_live.security.live_approval_gate import LiveApprovalGate
from paper_live.trade_facade import InternalTradeFacade


def _facade():
    controller = EnvironmentController()
    account = PaperAccount(Decimal("1000000"))
    gateway = ExecutionGateway(controller, VirtualMatchingEngine(account, slippage_bps=Decimal("0")))
    risk = RiskGuardian(controller, account, RiskLimits(max_order_notional=Decimal("500000")))
    secrets = SecretBroker(
        InMemorySecretStore({"toss-order": "x"}), SecretPolicy(live_secret_ids=frozenset({"toss-order"}))
    )
    return InternalTradeFacade(controller, risk, gateway, secret_broker=secrets)


def _request(port: int, method: str, path: str, body: dict | None = None, token: str = "test-token"):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "X-Internal-Token": token},
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.status, json.loads(resp.read().decode())


def test_health_requires_token_and_returns_snapshot():
    facade = _facade()
    server = create_internal_server(facade, internal_token="test-token", host="127.0.0.1", port=0)
    port = server.server_address[1]
    thread = __import__("threading").Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/internal/health", timeout=5)
        assert err.value.code == 401

        status, payload = _request(port, "GET", "/internal/health")
        assert status == 200
        assert payload["status"] == "ok"
        assert payload["mode"] == "PAPER_SANDBOX"
        assert payload["has_secret_broker"] is True
    finally:
        server.shutdown()


def test_preview_and_submit_paper_path_over_http():
    facade = _facade()
    server = create_internal_server(facade, internal_token="test-token", host="127.0.0.1", port=0)
    port = server.server_address[1]
    thread = __import__("threading").Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, preview = _request(
            port,
            "POST",
            "/internal/trade/preview",
            {
                "symbol": "005930",
                "side": "BUY",
                "quantity": "2",
                "price": "70000",
                "reference_price": "70000",
            },
        )
        assert status == 200
        assert preview["risk"]["approved"] is True
        assert preview["requires_approval"] is False
        assert preview["estimated_notional"] == "140000"
        assert "preview_id" in preview

        status, result = _request(
            port,
            "POST",
            "/internal/trade/submit",
            {
                "symbol": "005930",
                "side": "BUY",
                "quantity": "2",
                "reference_price": "1000",
                "client_order_id": "http-1",
            },
        )
        assert status == 200
        assert result["kind"] == "fill"
        assert result["quantity"] == "2"
        assert result["status"] == "FILLED"
    finally:
        server.shutdown()


def test_submit_risk_rejection_returns_403():
    facade = _facade()
    server = create_internal_server(facade, internal_token="test-token", host="127.0.0.1", port=0)
    port = server.server_address[1]
    thread = __import__("threading").Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/internal/trade/submit",
            data=json.dumps(
                {
                    "symbol": "005930",
                    "side": "BUY",
                    "quantity": "100",
                    "reference_price": "10000",
                    "client_order_id": "big",
                }
            ).encode(),
            method="POST",
            headers={"Content-Type": "application/json", "X-Internal-Token": "test-token"},
        )
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(req, timeout=5)
        assert err.value.code == 403
        body = json.loads(err.value.read().decode())
        assert body["error"]["code"] == "SUBMIT_DENIED"
    finally:
        server.shutdown()


class _FakeCancelBroker:
    name = "toss"

    def __init__(self):
        self.cancelled: list[str] = []

    def submit(self, request: BrokerOrderRequest) -> OrderResult:
        return OrderResult("toss", "ord-http", True, "ok")

    def cancel(self, order_id: str, *, symbol: str | None = None) -> bool:
        self.cancelled.append(order_id)
        return True


def test_cancel_over_http_requires_live_approval():
    import hashlib
    import hmac

    secret = "env-secret"
    token = hmac.new(secret.encode(), b"environment-transition", hashlib.sha256).hexdigest()
    from paper_live.live_approval import LiveApprovalGate as EnvGate

    env_gate = EnvGate()
    env_gate.approve("operator", "promote")
    controller = EnvironmentController(transition_secret=secret, live_approval_gate=env_gate)
    account = PaperAccount(Decimal("1000000"))
    gateway = ExecutionGateway(controller, VirtualMatchingEngine(account, slippage_bps=Decimal("0")))
    risk = RiskGuardian(controller, account, RiskLimits(max_order_notional=Decimal("500000")))
    order_gate = LiveApprovalGate()
    fake = _FakeCancelBroker()
    router = BrokerRouter({"toss": fake}, approval_gate=order_gate)
    secrets = SecretBroker(
        InMemorySecretStore({"toss-order": "x"}), SecretPolicy(live_secret_ids=frozenset({"toss-order"}))
    )
    facade = InternalTradeFacade(controller, risk, gateway, router, order_gate, secrets)
    controller.set_mode(ExecutionEnvironmentMode.REAL_LIVE, token)

    server = create_internal_server(facade, internal_token="test-token", host="127.0.0.1", port=0)
    port = server.server_address[1]
    thread = __import__("threading").Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/internal/trade/cancel",
            data=json.dumps({"broker": "toss", "order_id": "ord-http-1"}).encode(),
            method="POST",
            headers={"Content-Type": "application/json", "X-Internal-Token": "test-token"},
        )
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(req, timeout=5)
        assert err.value.code == 403
        body = json.loads(err.value.read().decode())
        assert body["error"]["code"] == "CANCEL_DENIED"

        approval = order_gate.approve("operator", order_gate.nonce)
        status, payload = _request(
            port,
            "POST",
            "/internal/trade/cancel",
            {"broker": "toss", "order_id": "ord-http-1", "approval_id": approval.approval_id},
        )
        assert status == 200
        assert payload == {
            "kind": "cancel_result",
            "broker": "toss",
            "order_id": "ord-http-1",
            "cancelled": True,
        }
        assert fake.cancelled == ["ord-http-1"]
    finally:
        server.shutdown()


def test_cancel_missing_order_id_returns_400():
    facade = _facade()
    server = create_internal_server(facade, internal_token="test-token", host="127.0.0.1", port=0)
    port = server.server_address[1]
    thread = __import__("threading").Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/internal/trade/cancel",
            data=json.dumps({"broker": "toss"}).encode(),
            method="POST",
            headers={"Content-Type": "application/json", "X-Internal-Token": "test-token"},
        )
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(req, timeout=5)
        assert err.value.code == 400
        body = json.loads(err.value.read().decode())
        assert body["error"]["code"] == "MISSING_ORDER_ID"
    finally:
        server.shutdown()
