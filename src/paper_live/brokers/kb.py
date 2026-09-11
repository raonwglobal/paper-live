from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass

from .protocol import BrokerAdapter, BrokerOrderRequest, OrderResult

BASE_URL = "https://developer.kbsec.com:32484"
DEFAULT_BUY_ORDER_PATH = "/api/v1/ssam1802"


class KbApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class KbCredentials:
    app_key: str
    app_secret: str
    order_path: str = DEFAULT_BUY_ORDER_PATH


class KbBrokerAdapter(BrokerAdapter):
    name = "kb"

    def __init__(self, credentials: KbCredentials | None = None, timeout: float = 10.0):
        self.credentials = credentials
        self._base_credentials = credentials
        self.timeout = timeout
        self._token: str | None = None
        self._ephemeral = False

    def apply_secret_material(self, material: str) -> None:
        from .credentials import parse_kb_credentials

        self.credentials = parse_kb_credentials(material)
        self._token = None
        self._ephemeral = True

    def clear_secret_material(self) -> None:
        if self._ephemeral:
            self.credentials = self._base_credentials
            self._token = None
            self._ephemeral = False

    @classmethod
    def from_env(cls) -> KbBrokerAdapter:
        return cls(
            KbCredentials(
                os.environ["KB_APP_KEY"], os.environ["KB_APP_SECRET"], os.getenv("KB_ORDER_PATH", DEFAULT_BUY_ORDER_PATH)
            )
        )

    def _require_credentials(self) -> KbCredentials:
        if self.credentials is None:
            raise PermissionError("KB credentials are not configured")
        return self.credentials

    def _token_value(self) -> str:
        if self._token:
            return self._token
        credentials = self._require_credentials()
        payload = json.dumps(
            {
                "grant_type": "client_credentials",
                "appKey": credentials.app_key,
                "appSecret": credentials.app_secret,
            }
        ).encode()
        req = urllib.request.Request(
            f"{BASE_URL}/oauth2/token", data=payload, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                self._token = json.load(response)["access_token"]
                return self._token
        except Exception as exc:
            raise KbApiError(str(exc)) from exc

    def _request(self, method: str, path: str, body: dict) -> dict:
        req = urllib.request.Request(
            f"{BASE_URL}{path}",
            data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {self._token_value()}", "Content-Type": "application/json"},
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return json.load(response)
        except Exception as exc:
            raise KbApiError(str(exc)) from exc

    def submit(self, request: BrokerOrderRequest) -> OrderResult:
        # The public KB guide identifies SSAM1802 as a buy-order endpoint, but
        # detailed request fields must come from the pinned official schema.
        # Do not guess mappings in a live-trading adapter.
        raise NotImplementedError("KB order mapping is blocked until the official JSON API schema is pinned")

    def cancel(self, order_id: str) -> bool:
        raise NotImplementedError("KB cancel endpoint must be mapped from the pinned KB API schema")
