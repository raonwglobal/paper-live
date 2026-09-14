"""Internal trade surface: Intent → Preview → Submit.

This is the process-local API for external gateways or in-process callers.
Secrets never appear in return values; REAL_LIVE submit resolves credentials
only through SecretBroker (optionally backed by GoogleDriveSecretStore).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN
from typing import Any
from uuid import uuid4

from .brokers.protocol import BrokerOrderRequest, OrderResult
from .brokers.safe_router import BrokerRouter
from .environment import EnvironmentController, ExecutionEnvironmentMode
from .execution import (
    ExecutionGateway,
    Fill,
    OrderSide,
    OrderType,
    PaperOrderRequest,
)
from .risk import RiskGuardian
from .secrets.broker import SecretBroker
from .security.live_approval_gate import LiveApprovalGate


@dataclass(frozen=True)
class OrderIntent:
    """Caller-facing order intent (gateway / agent contract)."""

    symbol: str
    side: str  # BUY | SELL
    quantity: Decimal
    order_type: str = "MARKET"  # MARKET | LIMIT
    price: Decimal | None = None
    broker: str = "toss"
    client_order_id: str = ""

    def normalized_side(self) -> OrderSide:
        value = self.side.strip().upper()
        if value not in {"BUY", "SELL"}:
            raise ValueError(f"invalid side: {self.side}")
        return OrderSide(value)

    def normalized_order_type(self) -> OrderType:
        value = self.order_type.strip().upper()
        if value not in {"MARKET", "LIMIT"}:
            raise ValueError(f"invalid order_type: {self.order_type}")
        return OrderType(value)


@dataclass(frozen=True)
class RiskAssessment:
    approved: bool
    level: str  # PASS | REJECT | BLOCKED
    violations: tuple[str, ...] = ()


@dataclass(frozen=True)
class OrderPreview:
    intent: OrderIntent
    estimated_notional: Decimal
    currency: str
    risk: RiskAssessment
    requires_approval: bool
    preview_id: str
    mode: str
    message: str = ""


@dataclass
class InternalTradeFacade:
    """Preview / submit orchestration for paper and live paths."""

    controller: EnvironmentController
    risk: RiskGuardian
    gateway: ExecutionGateway
    broker_router: BrokerRouter | None = None
    order_approval_gate: LiveApprovalGate | None = None
    secret_broker: SecretBroker | None = None
    """Maps broker id → secret_id used for order.create."""
    broker_secret_ids: dict[str, str] = field(default_factory=lambda: {"toss": "toss-order", "kb": "kb-order"})
    currency: str = "KRW"
    _previews: dict[str, OrderPreview] = field(default_factory=dict, init=False, repr=False)

    @staticmethod
    def intent_from_portfolio_row(
        row: dict[str, Any],
        *,
        account_value: Decimal,
        current_quantity: Decimal = Decimal("0"),
        broker: str = "toss",
        order_type: str = "MARKET",
        lot_size: Decimal = Decimal("1"),
    ) -> OrderIntent | None:
        """Convert a selected portfolio row into a delta-to-target order intent.

        ``target_weight`` is interpreted against account value. Quantity is
        rounded down to ``lot_size`` so the generated intent never exceeds the
        requested target notional. A zero delta returns ``None``.
        """
        symbol = str(row.get("symbol", "")).strip()
        if not symbol or account_value <= 0 or current_quantity < 0 or lot_size <= 0:
            raise ValueError("symbol, account_value, current_quantity and lot_size must be valid")
        try:
            weight = Decimal(str(row.get("target_weight", "0")))
            price = Decimal(str(row.get("close", row.get("price", "0"))))
        except Exception as exc:
            raise ValueError("portfolio row has invalid target_weight or price") from exc
        if weight < 0 or weight > 1 or price <= 0:
            raise ValueError("target_weight must be in [0, 1] and price must be positive")
        target_quantity = ((account_value * weight) / price / lot_size).to_integral_value(rounding=ROUND_DOWN) * lot_size
        delta = target_quantity - current_quantity
        if delta == 0:
            return None
        side = "BUY" if delta > 0 else "SELL"
        return OrderIntent(
            symbol=symbol,
            side=side,
            quantity=abs(delta),
            order_type=order_type,
            price=(price if order_type.strip().upper() == "LIMIT" else None),
            broker=broker,
        )

    def to_paper_order(self, intent: OrderIntent) -> PaperOrderRequest:
        client_id = intent.client_order_id or f"paper-{uuid4().hex[:16]}"
        return PaperOrderRequest(
            symbol=intent.symbol,
            side=intent.normalized_side(),
            quantity=intent.quantity,
            order_type=intent.normalized_order_type(),
            limit_price=intent.price,
            client_order_id=client_id,
        )

    def to_broker_order(self, intent: OrderIntent) -> BrokerOrderRequest:
        return BrokerOrderRequest(
            symbol=intent.symbol,
            side=intent.normalized_side().value,
            quantity=intent.quantity,
            order_type=intent.normalized_order_type().value,
            price=intent.price,
        )

    def _estimate_notional(self, intent: OrderIntent, reference_price: Decimal) -> Decimal:
        px = intent.price if intent.price is not None else reference_price
        return intent.quantity * px

    def _assess_risk(self, intent: OrderIntent, reference_price: Decimal) -> RiskAssessment:
        order = self.to_paper_order(intent)
        try:
            self.risk.approve(order, reference_price)
            return RiskAssessment(approved=True, level="PASS", violations=())
        except PermissionError as exc:
            return RiskAssessment(approved=False, level="REJECT", violations=(str(exc),))
        except ValueError as exc:
            return RiskAssessment(approved=False, level="REJECT", violations=(str(exc),))

    def preview(self, intent: OrderIntent, reference_price: Decimal) -> OrderPreview:
        if intent.quantity <= 0:
            raise ValueError("quantity must be positive")
        if reference_price <= 0 and intent.price is None:
            raise ValueError("reference_price or limit price is required")
        px = reference_price if reference_price > 0 else (intent.price or Decimal("0"))
        mode = self.controller.get_current_mode()
        risk = self._assess_risk(intent, px)
        requires_approval = mode is ExecutionEnvironmentMode.REAL_LIVE
        preview_id = f"prv-{uuid4().hex[:16]}"
        if risk.approved:
            message = (
                "REAL_LIVE requires approval_id; call submit with order approval."
                if requires_approval
                else "Risk passed; submit without approval_id on paper/virtual path."
            )
        else:
            message = "Risk rejected; submit will fail until limits are adjusted."
        preview = OrderPreview(
            intent=intent,
            estimated_notional=self._estimate_notional(intent, px),
            currency=self.currency,
            risk=risk,
            requires_approval=requires_approval,
            preview_id=preview_id,
            mode=mode.value,
            message=message,
        )
        self._previews[preview_id] = preview
        return preview

    def _resolve_live_secret(self, intent: OrderIntent, *, capability: str = "order.create") -> str:
        if self.secret_broker is None:
            raise PermissionError("SecretBroker is required for REAL_LIVE submit")
        secret_id = self.broker_secret_ids.get(intent.broker)
        if not secret_id:
            raise PermissionError(f"no secret mapping for broker: {intent.broker}")
        return self.secret_broker.resolve(
            secret_id=secret_id,
            mode=ExecutionEnvironmentMode.REAL_LIVE.value,
            capability=capability,
        )

    def _inject_credentials(self, intent: OrderIntent, *, capability: str = "order.create") -> object:
        """Resolve secret material and apply when the adapter supports injection.

        Resolve is always required (policy gate). Adapters without
        apply_secret_material still pass the gate (e.g. test doubles).
        """
        material = self._resolve_live_secret(intent, capability=capability)
        adapter = self._adapter_for(intent.broker)
        apply = getattr(adapter, "apply_secret_material", None)
        if apply is not None:
            apply(material)
        return adapter

    def _adapter_for(self, broker: str):
        if self.broker_router is None:
            raise PermissionError("BrokerRouter is not configured")
        adapter = self.broker_router.adapters.get(broker)
        if adapter is None:
            raise PermissionError(f"broker adapter is not configured: {broker}")
        return adapter

    def _submit_live(self, intent: OrderIntent, *, approval_id: str | None) -> OrderResult:
        if self.broker_router is None:
            raise PermissionError("BrokerRouter is not configured")
        if self.order_approval_gate is None or approval_id is None:
            raise PermissionError("explicit live approval_id is required")
        self.order_approval_gate.require(approval_id)
        adapter = self._inject_credentials(intent)
        try:
            request = self.to_broker_order(intent)
            return self.broker_router.submit(
                ExecutionEnvironmentMode.REAL_LIVE.value, intent.broker, request, approval_id
            )
        finally:
            clear = getattr(adapter, "clear_secret_material", None)
            if clear is not None:
                clear()

    def submit(
        self,
        intent: OrderIntent,
        reference_price: Decimal,
        *,
        approval_id: str | None = None,
        preview_id: str | None = None,
    ) -> Fill | OrderResult:
        mode = self.controller.get_current_mode()
        if preview_id is not None:
            stored = self._previews.get(preview_id)
            if stored is None:
                raise ValueError("unknown preview_id")
            if not stored.risk.approved:
                raise PermissionError("preview risk was not approved")
            intent = stored.intent

        risk = self._assess_risk(intent, reference_price)
        if not risk.approved:
            raise PermissionError("; ".join(risk.violations) or "risk rejected")

        if mode is ExecutionEnvironmentMode.REAL_LIVE:
            return self._submit_live(intent, approval_id=approval_id)

        paper_order = self.to_paper_order(intent)
        return self.gateway.execute(paper_order, reference_price)

    def cancel(
        self,
        *,
        broker: str,
        order_id: str,
        approval_id: str | None = None,
        symbol: str | None = None,
    ) -> bool:
        """Cancel a live order; paper path has no remote cancel (lifecycle only)."""
        mode = self.controller.get_current_mode()
        if mode is not ExecutionEnvironmentMode.REAL_LIVE:
            raise PermissionError("cancel via broker is only available in REAL_LIVE")
        if self.broker_router is None:
            raise PermissionError("BrokerRouter is not configured")
        if self.order_approval_gate is None or approval_id is None:
            raise PermissionError("explicit live approval_id is required")
        self.order_approval_gate.require(approval_id)
        intent = OrderIntent(
            symbol=(symbol or "-"),
            side="BUY",
            quantity=Decimal("1"),
            broker=broker,
        )
        adapter = self._inject_credentials(intent, capability="order.cancel")
        try:
            return self.broker_router.cancel(
                mode.value, broker, order_id, approval_id, symbol=symbol
            )
        finally:
            clear = getattr(adapter, "clear_secret_material", None)
            if clear is not None:
                clear()

    def snapshot(self) -> dict[str, Any]:
        mode = self.controller.get_current_mode()
        return {
            "mode": mode.value,
            "has_broker_router": self.broker_router is not None,
            "has_secret_broker": self.secret_broker is not None,
            "has_order_approval_gate": self.order_approval_gate is not None,
            "open_previews": len(self._previews),
        }
