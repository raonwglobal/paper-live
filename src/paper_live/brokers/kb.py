from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from decimal import Decimal

from .protocol import BrokerAdapter, BrokerOrderRequest, OrderResult

BASE_URL = "https://developer.kbsec.com:32484"
DEFAULT_BUY_ORDER_PATH = "/api/v1/ssam1802"
DEFAULT_SELL_ORDER_PATH = "/api/v1/ssam1801"
DEFAULT_MODIFY_ORDER_PATH = "/api/v1/ssam1805"
DEFAULT_CANCEL_ORDER_PATH = "/api/v1/ssam1806"


class KbApiError(RuntimeError):
    pass


class KbOrderSchemaUnavailable(RuntimeError):
    """Raised when a KB order schema is not pinned from authoritative documentation."""


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
        """Inject host-resolved credentials for the next gated live call."""
        from .credentials import parse_kb_credentials

        self.credentials = parse_kb_credentials(material)
        self._token = None
        self._ephemeral = True

    def clear_secret_material(self) -> None:
        """Drop ephemeral credentials after a gated submit/cancel."""
        if self._ephemeral:
            self.credentials = self._base_credentials
            self._token = None
            self._ephemeral = False

    @classmethod
    def from_env(cls) -> KbBrokerAdapter:
        return cls(
            KbCredentials(
                os.environ["KB_APP_KEY"],
                os.environ["KB_APP_SECRET"],
                os.getenv("KB_ORDER_PATH", DEFAULT_BUY_ORDER_PATH),
            )
        )

    def _require_credentials(self) -> KbCredentials:
        if self.credentials is None:
            raise PermissionError("KB credentials are not configured")
        return self.credentials

    def _live_enabled(self) -> bool:
        return os.getenv("PAPER_LIVE_ENABLE_LIVE", "").strip().lower() in {"1", "true", "yes"}

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
            f"{BASE_URL}/oauth2/token",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                payload_obj = json.load(response)
        except Exception as exc:
            raise KbApiError(f"KB token request failed: {type(exc).__name__}") from exc
        token = payload_obj.get("access_token") if isinstance(payload_obj, dict) else None
        if not isinstance(token, str) or not token.strip():
            raise KbApiError("KB token response did not contain access_token")
        self._token = token.strip()
        return self._token

    def _request(self, method: str, path: str, body: dict) -> dict:
        self._require_credentials()
        req = urllib.request.Request(
            f"{BASE_URL}{path}",
            data=json.dumps(body).encode(),
            headers={
                "Authorization": f"Bearer {self._token_value()}",
                "Content-Type": "application/json",
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                payload = json.load(response)
        except Exception as exc:
            raise KbApiError(f"KB API request failed: {type(exc).__name__}") from exc
        if not isinstance(payload, dict):
            raise KbApiError("KB API response was not a JSON object")
        return payload

    @staticmethod
    def _validate_order(request: BrokerOrderRequest) -> tuple[str, str]:
        side = request.side.strip().upper()
        order_type = request.order_type.strip().upper()
        if side not in {"BUY", "SELL"} or order_type not in {"LIMIT", "MARKET"}:
            raise ValueError("unsupported KB order request")
        if not request.symbol.strip():
            raise ValueError("symbol is required")
        if request.quantity <= 0:
            raise ValueError("quantity must be positive")
        if order_type == "LIMIT" and (request.price is None or request.price <= 0):
            raise ValueError("limit orders require a positive price")
        if order_type == "MARKET" and request.price is not None:
            raise ValueError("market orders must not include price")
        return side, order_type

    @staticmethod
    def _path_for_side(side: str) -> str:
        return DEFAULT_BUY_ORDER_PATH if side == "BUY" else DEFAULT_SELL_ORDER_PATH

    @staticmethod
    def _build_order_body(request: BrokerOrderRequest, side: str, order_type: str) -> dict[str, str]:
        """Refuse to serialize fields whose KB names have not been authoritatively pinned."""
        del request, side, order_type
        raise KbOrderSchemaUnavailable(
            "KB SSAM1801/SSAM1802 request fields are not fully pinned; refusing to guess order payload"
        )

    @staticmethod
    def _result_from_response(response: dict) -> OrderResult:
        order_id = response.get("ordr_no")
        msg = response.get("o_msg")
        message = msg.strip() if isinstance(msg, str) else ""
        if not isinstance(order_id, str) or not order_id.strip():
            return OrderResult("kb", "", False, message or "KB API response did not contain ordr_no")
        return OrderResult("kb", order_id.strip(), True, message)

    def submit(
        self,
        request_or_symbol: BrokerOrderRequest | str,
        side: str | None = None,
        quantity: Decimal | None = None,
        price: Decimal | None = None,
    ) -> OrderResult:
        """Validate intent but fail closed until the complete KB order schema is pinned."""
        if not self._live_enabled():
            raise PermissionError("KB live execution is disabled by default")
        if isinstance(request_or_symbol, BrokerOrderRequest):
            request = request_or_symbol
        else:
            if side is None or quantity is None:
                raise ValueError("side and quantity are required")
            request = BrokerOrderRequest(
                str(request_or_symbol),
                side,
                quantity,
                "limit" if price is not None else "market",
                price,
            )
        side_n, order_type = self._validate_order(request)
        self._build_order_body(request, side_n, order_type)
        raise AssertionError("unreachable")

    def cancel(self, order_id: str, *, symbol: str | None = None) -> bool:
        """Fail closed until the complete SSAM1806 cancel schema is pinned."""
        if not self._live_enabled():
            raise PermissionError("KB live execution is disabled by default")
        if not order_id.strip():
            raise ValueError("order_id is required")
        if symbol is None or not str(symbol).strip() or str(symbol).strip() == "-":
            raise ValueError("symbol is required for KB cancel")
        raise KbOrderSchemaUnavailable(
            "KB SSAM1806 cancel fields are not fully pinned; refusing to guess cancel payload"
        )
