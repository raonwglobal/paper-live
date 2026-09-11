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
        self._base_credentials = credentials
        self.timeout = timeout
        self._token: str | None = None
        self._ephemeral = False

    def apply_secret_material(self, material: str) -> None:
        """Inject host-resolved credentials for the next live calls; not for agents."""
        from .credentials import parse_toss_credentials

        self.credentials = parse_toss_credentials(material)
        self._token = None
        self._ephemeral = True

    def clear_secret_material(self) -> None:
        """Drop ephemeral credentials after a gated submit/cancel."""
        if self._ephemeral:
            self.credentials = self._base_credentials
            self._token = None
            self._ephemeral = False

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
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                payload = json.load(response)
        except Exception as exc:
            raise TossApiError(f"token request failed: {type(exc).__name__}") from exc
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise TossApiError("token response did not contain access_token")
        self._token = token
        return token

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
                payload = json.load(response)
        except Exception as exc:
            raise TossApiError(f"Toss API request failed: {type(exc).__name__}") from exc
        if not isinstance(payload, dict):
            raise TossApiError("Toss API response was not a JSON object")
        return payload

    @staticmethod
    def _validate_order(request: BrokerOrderRequest) -> tuple[str, str]:
        side = request.side.strip().upper()
        order_type = request.order_type.strip().upper()
        if side not in {"BUY", "SELL"} or order_type not in {"LIMIT", "MARKET"}:
            raise ValueError("unsupported Toss order request")
        if not request.symbol.strip():
            raise ValueError("symbol is required")
        if request.quantity <= 0:
            raise ValueError("quantity must be positive")
        if order_type == "LIMIT":
            if request.price is None or request.price <= 0:
                raise ValueError("limit orders require a positive price")
        elif request.price is not None:
            raise ValueError("market orders must not include price")
        return side, order_type

    @staticmethod
    def _result_from_response(response: dict) -> OrderResult:
        result = response.get("result")
        if not isinstance(result, dict):
            return OrderResult("toss", "", False, "Toss API response did not contain result")
        order_id = result.get("orderId")
        if not isinstance(order_id, str) or not order_id.strip():
            return OrderResult("toss", "", False, "Toss API response did not contain orderId")
        return OrderResult("toss", order_id, True)

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
                str(request_or_symbol), side, quantity, "limit" if price is not None else "market", price
            )
        side, order_type = self._validate_order(request)
        payload = {
            "symbol": request.symbol,
            "side": side,
            "orderType": order_type,
            "quantity": str(request.quantity),
        }
        if request.price is not None:
            payload["price"] = str(request.price)
        return self._result_from_response(self._request("POST", "/api/v1/orders", payload))

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
        if quantity is not None and quantity <= 0:
            raise ValueError("quantity must be positive")
        if order_amount is not None and order_amount <= 0:
            raise ValueError("order_amount must be positive")
        request = BrokerOrderRequest(symbol, side, quantity or Decimal("1"), order_type, price)
        normalized_side, normalized_type = self._validate_order(request)
        payload = {"symbol": symbol, "side": normalized_side, "orderType": normalized_type}
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
        return self._result_from_response(self._request("POST", "/api/v1/orders", payload))

    def cancel(self, order_id: str) -> bool:
        if not self._live_enabled():
            raise PermissionError("Toss live execution is disabled by default")
        if not order_id.strip():
            raise ValueError("order_id is required")
        self._request("POST", f"/api/v1/orders/{urllib.parse.quote(order_id, safe='')}/cancel")
        return True
