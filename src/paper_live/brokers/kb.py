from __future__ import annotations
import json, os, urllib.request
from dataclasses import dataclass
from decimal import Decimal
from .protocol import BrokerAdapter, OrderRequest, OrderResult

BASE_URL = "https://developer.kbsec.com:32484"

class KbApiError(RuntimeError):
    pass

@dataclass(frozen=True)
class KbCredentials:
    app_key: str
    app_secret: str
    order_path: str = "/api/v1/ssqm1802"

class KbBrokerAdapter(BrokerAdapter):
    name = "kb"

    def __init__(self, credentials: KbCredentials, timeout: float = 10.0):
        self.credentials = credentials
        self.timeout = timeout
        self._token: str | None = None

    @classmethod
    def from_env(cls) -> "KbBrokerAdapter":
        return cls(KbCredentials(os.environ["KB_APP_KEY"], os.environ["KB_APP_SECRET"], os.getenv("KB_ORDER_PATH", "/api/v1/ssqm1802")))

    def _token_value(self) -> str:
        if self._token:
            return self._token
        payload = json.dumps({"grant_type": "client_credentials", "appKey": self.credentials.app_key, "appSecret": self.credentials.app_secret}).encode()
        req = urllib.request.Request(f"{BASE_URL}/oauth2/token", data=payload, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                self._token = json.load(response)["access_token"]
                return self._token
        except Exception as exc:
            raise KbApiError(str(exc)) from exc

    def _request(self, method: str, path: str, body: dict) -> dict:
        req = urllib.request.Request(f"{BASE_URL}{path}", data=json.dumps(body).encode(), headers={"Authorization": f"Bearer {self._token_value()}", "Content-Type": "application/json"}, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return json.load(response)
        except Exception as exc:
            raise KbApiError(str(exc)) from exc

    def submit(self, request: OrderRequest) -> OrderResult:
        # KB's public guide confirms ssqm1802 as an order endpoint, but the
        # downloadable API schema is authoritative for exact body field names.
        # Keep the broker-specific mapping isolated until that schema is pinned.
        body = {"dataHeader": {}, "dataBody": {"symbol": request.symbol, "side": request.side, "quantity": str(request.quantity), "orderType": request.order_type}}
        response = self._request("POST", self.credentials.order_path, body)
        return OrderResult(self.name, str(response.get("orderId") or response.get("dataBody", {}).get("orderId", "")), True)

    def cancel(self, order_id: str) -> bool:
        raise NotImplementedError("KB cancel endpoint must be mapped from the pinned KB API schema")
