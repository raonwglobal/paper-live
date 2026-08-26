from __future__ import annotations
import base64, json, os, urllib.parse, urllib.request
from dataclasses import dataclass
from decimal import Decimal
from .protocol import BrokerAdapter, OrderRequest, OrderResult

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

    def __init__(self, credentials: TossCredentials, timeout: float = 10.0):
        self.credentials = credentials
        self.timeout = timeout
        self._token: str | None = None

    @classmethod
    def from_env(cls) -> "TossBrokerAdapter":
        return cls(TossCredentials(os.environ["TOSS_CLIENT_ID"], os.environ["TOSS_CLIENT_SECRET"], os.environ["TOSS_ACCOUNT_SEQ"]))

    def _token_value(self) -> str:
        if self._token:
            return self._token
        body = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
        auth = base64.b64encode(f"{self.credentials.client_id}:{self.credentials.client_secret}".encode()).decode()
        req = urllib.request.Request(f"{BASE_URL}/oauth2/token", data=body, headers={"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            payload = json.load(response)
        self._token = payload["access_token"]
        return self._token

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self._token_value()}", "Content-Type": "application/json", "X-Tossinvest-Account": self.credentials.account_seq}
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return json.load(response)
        except Exception as exc:
            raise TossApiError(str(exc)) from exc

    def submit(self, request: OrderRequest) -> OrderResult:
        if request.side not in {"BUY", "SELL"} or request.order_type.upper() not in {"LIMIT", "MARKET"}:
            raise ValueError("unsupported Toss order request")
        payload = {"symbol": request.symbol, "side": request.side, "orderType": request.order_type.upper(), "quantity": str(request.quantity)}
        if request.order_type.upper() == "LIMIT":
            raise ValueError("Toss LIMIT requires price; use submit_typed_order")
        response = self._request("POST", "/api/v1/orders", payload)
        result = response.get("result", {})
        return OrderResult(self.name, result.get("orderId", ""), True)

    def submit_typed_order(self, *, symbol: str, side: str, order_type: str, quantity: Decimal | None = None, price: Decimal | None = None, order_amount: Decimal | None = None, client_order_id: str | None = None, time_in_force: str | None = None) -> OrderResult:
        if (quantity is None) == (order_amount is None):
            raise ValueError("exactly one of quantity or order_amount is required")
        payload = {"symbol": symbol, "side": side, "orderType": order_type}
        if quantity is not None: payload["quantity"] = str(quantity)
        if order_amount is not None: payload["orderAmount"] = str(order_amount)
        if price is not None: payload["price"] = str(price)
        if client_order_id: payload["clientOrderId"] = client_order_id
        if time_in_force: payload["timeInForce"] = time_in_force
        result = self._request("POST", "/api/v1/orders", payload).get("result", {})
        return OrderResult(self.name, result.get("orderId", ""), True)

    def cancel(self, order_id: str) -> bool:
        self._request("POST", f"/api/v1/orders/{urllib.parse.quote(order_id, safe='')}/cancel")
        return True
