from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
import json
import os
from urllib.request import Request, urlopen

from .security import CredentialProvider, BrokerCredentials


@dataclass(frozen=True)
class BrokerOrderResult:
    broker: str
    broker_order_id: str
    status: str
    raw: dict


class BrokerAdapter(ABC):
    name: str

    @abstractmethod
    def submit(self, symbol: str, side: str, quantity: Decimal, price: Decimal | None = None) -> BrokerOrderResult:
        raise NotImplementedError


class _GuardedHTTPBroker(BrokerAdapter):
    live_env = "PAPER_LIVE_ENABLE_LIVE"

    def _assert_live_enabled(self) -> None:
        if os.getenv(self.live_env, "false").lower() != "true":
            raise PermissionError("live broker execution is disabled; set PAPER_LIVE_ENABLE_LIVE=true only in an explicitly authorized deployment")

    @staticmethod
    def _post(url: str, headers: dict[str, str], payload: dict) -> dict:
        req = Request(url, data=json.dumps(payload).encode("utf-8"), headers={**headers, "Content-Type": "application/json"}, method="POST")
        with urlopen(req, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))


class TossBrokerAdapter(_GuardedHTTPBroker):
    """Toss Securities Open API order adapter.

    Official documentation currently exposes POST /v1/orders with Bearer token
    and X-Tossinvest-Account headers. Actual live execution remains opt-in.
    """

    name = "toss"

    def __init__(self, credentials: BrokerCredentials | None = None):
        self.credentials = credentials or CredentialProvider().load_toss()
        self.base_url = os.getenv("TOSS_API_BASE_URL", "https://openapi.tossinvest.com/v1")

    def submit(self, symbol: str, side: str, quantity: Decimal, price: Decimal | None = None) -> BrokerOrderResult:
        self._assert_live_enabled()
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        if price is None or price <= 0:
            raise ValueError("price is required for the current guarded LIMIT adapter")
        payload = {"symbol": symbol, "side": side, "orderType": "LIMIT", "quantity": int(quantity), "price": float(price)}
        raw = self._post(f"{self.base_url.rstrip('/')}/orders", {"Authorization": f"Bearer {self.credentials.access_token}", "X-Tossinvest-Account": self.credentials.account_id}, payload)
        order_id = str(raw.get("orderId") or raw.get("id") or "")
        return BrokerOrderResult(self.name, order_id, str(raw.get("status", "SUBMITTED")), raw)


class KBBrokerAdapter(_GuardedHTTPBroker):
    """KB adapter boundary with deployment-configured endpoint/payload mapping.

    KB Fintech Store requires partner registration/test-bed credentials; the
    endpoint is therefore not hard-coded from public login pages.
    """

    name = "kb"

    def __init__(self, credentials: BrokerCredentials | None = None):
        self.credentials = credentials or CredentialProvider().load_kb()
        self.base_url = os.getenv("KB_API_BASE_URL", "").rstrip("/")
        if not self.base_url:
            raise RuntimeError("KB_API_BASE_URL must be configured from the approved KB API product")
        self.order_path = os.getenv("KB_ORDER_PATH", "/orders")

    def submit(self, symbol: str, side: str, quantity: Decimal, price: Decimal | None = None) -> BrokerOrderResult:
        self._assert_live_enabled()
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        payload = {"symbol": symbol, "side": side, "quantity": str(quantity)}
        if price is not None:
            payload["price"] = str(price)
        raw = self._post(f"{self.base_url}{self.order_path}", {"Authorization": f"Bearer {self.credentials.access_token}"}, payload)
        order_id = str(raw.get("orderId") or raw.get("id") or "")
        return BrokerOrderResult(self.name, order_id, str(raw.get("status", "SUBMITTED")), raw)
