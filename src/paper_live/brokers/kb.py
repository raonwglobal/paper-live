from __future__ import annotations
import json, os, urllib.request
from dataclasses import dataclass
from .protocol import BrokerAdapter, BrokerOrderRequest, OrderResult

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

    def submit(self, request: BrokerOrderRequest) -> OrderResult:
        # The public KB guide identifies ssqm1802 as an order endpoint, but
        # explicitly states that the detailed request fields are finalized by
        # the official API specification. Do not guess field mappings in a
        # live-trading adapter. The pinned KB JSON schema must supply them.
        raise NotImplementedError("KB order mapping is blocked until the official JSON API schema is pinned")

    def cancel(self, order_id: str) -> bool:
        raise NotImplementedError("KB cancel endpoint must be mapped from the pinned KB API schema")
