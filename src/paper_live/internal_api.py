"""Minimal internal HTTP surface for process-boundary callers.

Stdlib only (no FastAPI). Bind to loopback or a private network.
Secrets and tokens never appear in response bodies.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, is_dataclass
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from .brokers.protocol import OrderResult
from .execution import Fill
from .trade_facade import InternalTradeFacade, OrderIntent, OrderPreview


class InternalApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if hasattr(value, "value"):
        return value.value
    raise TypeError(f"not JSON serializable: {type(value)!r}")


def _serialize_preview(preview: OrderPreview) -> dict[str, Any]:
    return {
        "preview_id": preview.preview_id,
        "mode": preview.mode,
        "currency": preview.currency,
        "estimated_notional": str(preview.estimated_notional),
        "requires_approval": preview.requires_approval,
        "message": preview.message,
        "risk": {
            "approved": preview.risk.approved,
            "level": preview.risk.level,
            "violations": list(preview.risk.violations),
        },
        "intent": {
            "symbol": preview.intent.symbol,
            "side": preview.intent.side,
            "quantity": str(preview.intent.quantity),
            "order_type": preview.intent.order_type,
            "price": str(preview.intent.price) if preview.intent.price is not None else None,
            "broker": preview.intent.broker,
            "client_order_id": preview.intent.client_order_id or None,
        },
    }


def _serialize_fill(fill: Fill) -> dict[str, Any]:
    return {
        "kind": "fill",
        "order_id": fill.order_id,
        "symbol": fill.symbol,
        "side": fill.side.value,
        "quantity": str(fill.quantity),
        "price": str(fill.price),
        "fee": str(fill.fee),
        "tax": str(fill.tax),
        "status": fill.status,
    }


def _serialize_order_result(result: OrderResult) -> dict[str, Any]:
    return {
        "kind": "broker_result",
        "broker": result.broker,
        "order_id": result.order_id,
        "accepted": result.accepted,
        "message": result.message,
    }


def _parse_intent(body: dict[str, Any]) -> OrderIntent:
    try:
        quantity = Decimal(str(body["quantity"]))
    except (KeyError, InvalidOperation) as exc:
        raise InternalApiError(400, "INVALID_QUANTITY", "quantity is required and must be numeric") from exc
    price_raw = body.get("price")
    price = Decimal(str(price_raw)) if price_raw is not None and price_raw != "" else None
    return OrderIntent(
        symbol=str(body.get("symbol", "")).strip(),
        side=str(body.get("side", "")).strip(),
        quantity=quantity,
        order_type=str(body.get("order_type", body.get("orderType", "MARKET"))),
        price=price,
        broker=str(body.get("broker", "toss")).strip().lower() or "toss",
        client_order_id=str(body.get("client_order_id", body.get("clientOrderId", "")) or ""),
    )


def _parse_reference_price(body: dict[str, Any]) -> Decimal:
    raw = body.get("reference_price", body.get("referencePrice"))
    if raw is None:
        raise InternalApiError(400, "MISSING_REFERENCE_PRICE", "reference_price is required")
    try:
        value = Decimal(str(raw))
    except InvalidOperation as exc:
        raise InternalApiError(400, "INVALID_REFERENCE_PRICE", "reference_price must be numeric") from exc
    if value <= 0:
        raise InternalApiError(400, "INVALID_REFERENCE_PRICE", "reference_price must be positive")
    return value


class InternalApiApp:
    """Shared application state for the internal HTTP handlers."""

    def __init__(self, facade: InternalTradeFacade, *, internal_token: str):
        if not internal_token or not internal_token.strip():
            raise ValueError("internal_token is required")
        self.facade = facade
        self.internal_token = internal_token.strip()

    def authorize(self, headers: dict[str, str]) -> None:
        provided = headers.get("X-Internal-Token") or headers.get("x-internal-token") or ""
        if provided != self.internal_token:
            raise InternalApiError(401, "UNAUTHORIZED", "valid x-internal-token is required")

    def health(self) -> dict[str, Any]:
        snap = self.facade.snapshot()
        return {"status": "ok", **snap}

    def preview(self, body: dict[str, Any]) -> dict[str, Any]:
        intent = _parse_intent(body)
        if not intent.symbol:
            raise InternalApiError(400, "MISSING_SYMBOL", "symbol is required")
        reference_price = _parse_reference_price(body)
        try:
            preview = self.facade.preview(intent, reference_price)
        except ValueError as exc:
            raise InternalApiError(400, "PREVIEW_REJECTED", str(exc)) from exc
        return _serialize_preview(preview)

    def submit(self, body: dict[str, Any]) -> dict[str, Any]:
        intent = _parse_intent(body)
        if not intent.symbol and not body.get("preview_id"):
            raise InternalApiError(400, "MISSING_SYMBOL", "symbol or preview_id is required")
        reference_price = _parse_reference_price(body)
        approval_id = body.get("approval_id") or body.get("approvalId")
        preview_id = body.get("preview_id") or body.get("previewId")
        try:
            result = self.facade.submit(
                intent,
                reference_price,
                approval_id=str(approval_id) if approval_id else None,
                preview_id=str(preview_id) if preview_id else None,
            )
        except PermissionError as exc:
            raise InternalApiError(403, "SUBMIT_DENIED", str(exc)) from exc
        except ValueError as exc:
            raise InternalApiError(400, "SUBMIT_REJECTED", str(exc)) from exc
        if isinstance(result, Fill):
            return _serialize_fill(result)
        return _serialize_order_result(result)

    def cancel(self, body: dict[str, Any]) -> dict[str, Any]:
        broker = str(body.get("broker", "toss")).strip().lower() or "toss"
        order_id = str(body.get("order_id") or body.get("orderId") or "").strip()
        if not order_id:
            raise InternalApiError(400, "MISSING_ORDER_ID", "order_id is required")
        approval_id = body.get("approval_id") or body.get("approvalId")
        try:
            ok = self.facade.cancel(
                broker=broker,
                order_id=order_id,
                approval_id=str(approval_id) if approval_id else None,
            )
        except PermissionError as exc:
            raise InternalApiError(403, "CANCEL_DENIED", str(exc)) from exc
        except ValueError as exc:
            raise InternalApiError(400, "CANCEL_REJECTED", str(exc)) from exc
        return {"kind": "cancel_result", "broker": broker, "order_id": order_id, "cancelled": bool(ok)}


def make_handler(app: InternalApiApp) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            # Keep CI/test output quiet; operators can wrap with a logger later.
            return

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length <= 0:
                return {}
            if length > 1_000_000:
                raise InternalApiError(413, "PAYLOAD_TOO_LARGE", "request body too large")
            raw = self.rfile.read(length)
            try:
                data = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise InternalApiError(400, "INVALID_JSON", "request body must be JSON") from exc
            if not isinstance(data, dict):
                raise InternalApiError(400, "INVALID_JSON", "JSON object required")
            return data

        def _write_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False, default=_json_default).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _write_error(self, err: InternalApiError) -> None:
            self._write_json(err.status, {"error": {"code": err.code, "message": err.message}})

        def do_GET(self) -> None:  # noqa: N802
            try:
                path = urlparse(self.path).path
                headers = {k: v for k, v in self.headers.items()}
                app.authorize(headers)
                if path in {"/internal/health", "/health"}:
                    self._write_json(200, app.health())
                    return
                raise InternalApiError(404, "NOT_FOUND", f"unknown path: {path}")
            except InternalApiError as err:
                self._write_error(err)

        def do_POST(self) -> None:  # noqa: N802
            try:
                path = urlparse(self.path).path
                headers = {k: v for k, v in self.headers.items()}
                app.authorize(headers)
                body = self._read_json()
                if path == "/internal/trade/preview":
                    self._write_json(200, app.preview(body))
                    return
                if path == "/internal/trade/submit":
                    self._write_json(200, app.submit(body))
                    return
                if path == "/internal/trade/cancel":
                    self._write_json(200, app.cancel(body))
                    return
                raise InternalApiError(404, "NOT_FOUND", f"unknown path: {path}")
            except InternalApiError as err:
                self._write_error(err)

    return Handler


def create_internal_server(
    facade: InternalTradeFacade,
    *,
    internal_token: str,
    host: str = "127.0.0.1",
    port: int = 0,
) -> ThreadingHTTPServer:
    """Create a ThreadingHTTPServer. port=0 binds an ephemeral port."""
    app = InternalApiApp(facade, internal_token=internal_token)
    handler = make_handler(app)
    return ThreadingHTTPServer((host, port), handler)


def serve_internal_api(
    facade: InternalTradeFacade,
    *,
    internal_token: str,
    host: str = "127.0.0.1",
    port: int = 8787,
) -> ThreadingHTTPServer:
    """Start the internal API in a daemon thread; returns the server instance."""
    server = create_internal_server(facade, internal_token=internal_token, host=host, port=port)
    thread = threading.Thread(target=server.serve_forever, name="paper-live-internal-api", daemon=True)
    thread.start()
    return server
