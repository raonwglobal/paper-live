from __future__ import annotations

import base64
import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from decimal import Decimal

from .protocol import BrokerAdapter, BrokerOrderRequest, OrderResult

BASE_URL = "https://openapi.tossinvest.com"


class TossApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class TossCredentials:
    client_id: str
    client_secret: str
    account_seq: str


class TossBrokerAdapter(BrokerAdapter):
    name = "toss"

    def __init__(self, credentials: TossCredentials | None = None, timeout: float = 10.0):
        self.credentials = credentials
        self.timeout = timeout
        self._token: str | None = None

    @classmethod
    def from_env(cls) -> TossBrokerAdapter:
        return cls(
            TossCredentials(
                os.environ["TOSS_CLIENT_ID"], os.environ["TOSS_CLIENT_SECRET"], os.environ["TOSS_ACCOUNT_SEQ"]
            )
        )

    def _require_credentials(self) -> TossCredentials:
        if self.credentials is None:
            raise PermissionError("Toss credentials are not configured")
        return self.credentials

    def _live_enabled(self) -> bool:
        return os.getenv("PAPER_LIVE_ENABLE_LIVE", "").strip().lower() in {"1", "true", "yes"}

    def _token_value(self) -> str:
        credentials = self._require_credentials()
        if self._token:
            return self._token
        body = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
        auth = base64.b64encode(f"{credentials.client_id}:{credentials.client_secret}".encode()).decode()
        req = urllib.request.Request(
            f"{BASE_URL}/oauth2/token",
            data=body,
            headers={"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            payload = json.load(response)
        self._token = payload["access_token"]
        return self._token

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        credentials = self._require_credentials()
        headers = {
            "Authorization": f"Bearer {self._token_value()}",
            "Content-Type": "application/json",
            "X-Tossinvest-Account": credentials.account_seq,
        }
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return json.load(response)
        except Exception as exc:
            raise TossApiError(str(exc)) from exc

    def submit(
        self,
        request_or_symbol: BrokerOrderRequest | str,
        side: str | None = None,
        quantity: Decimal | None = None,
        price: Decimal | None = None,
    ) -> OrderResult:
        """Submit an order only when live execution is explicitly enabled.

        Accepts BrokerOrderRequest and a legacy positional form for compatibility.
        """
        if not self._live_enabled():
            raise PermissionError("Toss live execution is disabled by default")
        if isinstance(request_or_symbol, BrokerOrderRequest):
            request = request_or_symbol
        else:
            if side is None or quantity is None:
                raise ValueError("side and quantity are required")
            request = BrokerOrderRequest(
                str(request_or_symbol), side, quantity, "limit" if price is not None else "market"
            )
        if request.side not in {"BUY", "SELL"} or request.order_type.upper() not in {"LIMIT", "MARKET"}:
            raise ValueError("unsupported Toss order request")
        payload = {
            "symbol": request.symbol,
            "side": request.side,
            "orderType": request.order_type.upper(),
            "quantity": str(request.quantity),
        }
        if price is not None:
            payload["price"] = str(price)
        response = self._request("POST", "/api/v1/orders", payload)
        result = response.get("result", {})
        return OrderResult(self.name, result.get("orderId", ""), True)

    def submit_typed_order(
        self,
        *,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal | None = None,
        price: Decimal | None = None,
        order_amount: Decimal | None = None,
        client_order_id: str | None = None,
        time_in_force: str | None = None,
    ) -> OrderResult:
        if not self._live_enabled():
            raise PermissionError("Toss live execution is disabled by default")
        if (quantity is None) == (order_amount is None):
            raise ValueError("exactly one of quantity or order_amount is required")
        payload = {"symbol": symbol, "side": side, "orderType": order_type}
        if quantity is not None:
            payload["quantity"] = str(quantity)
        if order_amount is not None:
            payload["orderAmount"] = str(order_amount)
        if price is not None:
            payload["price"] = str(price)
        if client_order_id:
            payload["clientOrderId"] = client_order_id
        if time_in_force:
            payload["timeInForce"] = time_in_force
        result = self._request("POST", "/api/v1/orders", payload).get("result", {})
        return OrderResult(self.name, result.get("orderId", ""), True)

    def cancel(self, order_id: str) -> bool:
        if not self._live_enabled():
            raise PermissionError("Toss live execution is disabled by default")
        self._request("POST", f"/api/v1/orders/{urllib.parse.quote(order_id, safe='')}/cancel")
        return True
