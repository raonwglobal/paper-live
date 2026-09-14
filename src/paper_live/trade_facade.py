"""Internal trade surface: Intent → Preview → Submit."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal, ROUND_DOWN
from typing import Any, Mapping
from uuid import uuid4

from .brokers.protocol import BrokerOrderRequest, OrderResult
from .brokers.safe_router import BrokerRouter
from .environment import EnvironmentController, ExecutionEnvironmentMode
from .execution import ExecutionGateway, Fill, OrderSide, OrderType, PaperAccount, PaperOrderRequest
from .execution_audit import ExecutionAuditRecord, ExecutionAuditTrail
from .portfolio_risk import PortfolioRiskContextBuilder, PortfolioRiskSnapshot
from .risk import PortfolioRiskContext, RiskGuardian
from .secrets.broker import SecretBroker
from .security.live_approval_gate import LiveApprovalGate


@dataclass(frozen=True)
class OrderIntent:
    symbol: str
    side: str
    quantity: Decimal
    order_type: str = "MARKET"
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
    level: str
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


@dataclass(frozen=True)
class PortfolioRevalidation:
    """Final pre-trade state used to re-check a recommendation."""

    snapshot: PortfolioRiskSnapshot
    intent: OrderIntent | None
    preview: OrderPreview | None


@dataclass
class InternalTradeFacade:
    controller: EnvironmentController
    risk: RiskGuardian
    gateway: ExecutionGateway
    broker_router: BrokerRouter | None = None
    order_approval_gate: LiveApprovalGate | None = None
    secret_broker: SecretBroker | None = None
    broker_secret_ids: dict[str, str] = field(default_factory=lambda: {"toss": "toss-order", "kb": "kb-order"})
    currency: str = "KRW"
    portfolio_risk_builder: PortfolioRiskContextBuilder = field(default_factory=PortfolioRiskContextBuilder)
    audit_trail: ExecutionAuditTrail | None = None
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
        normalized_type = order_type.strip().upper()
        return OrderIntent(symbol=symbol, side="BUY" if delta > 0 else "SELL", quantity=abs(delta), order_type=order_type, price=(price if normalized_type == "LIMIT" else None), broker=broker)

    def build_portfolio_risk_context(self, account: PaperAccount, prices: Mapping[str, Decimal], *, markets: Mapping[str, str] | None = None, target_symbol: str | None = None) -> PortfolioRiskSnapshot:
        return self.portfolio_risk_builder.build(account, prices, markets=markets, target_symbol=target_symbol)

    def preview_portfolio_row(self, row: dict[str, Any], *, account: PaperAccount, prices: Mapping[str, Decimal], markets: Mapping[str, str] | None = None, broker: str = "toss", order_type: str = "MARKET", lot_size: Decimal = Decimal("1")) -> OrderPreview | None:
        symbol = str(row.get("symbol", "")).strip()
        snapshot = self.build_portfolio_risk_context(account, prices, markets=markets, target_symbol=symbol)
        intent = self.intent_from_portfolio_row(row, account_value=snapshot.context.account_value, current_quantity=account.positions.get(symbol, Decimal("0")), broker=broker, order_type=order_type, lot_size=lot_size)
        if intent is None:
            return None
        reference_price = Decimal(str(prices.get(intent.symbol, "0")))
        return self.preview(intent, reference_price, portfolio_context=snapshot.context)

    def revalidate_portfolio_row(self, row: dict[str, Any], *, account: PaperAccount, latest_prices: Mapping[str, Decimal], markets: Mapping[str, str] | None = None, broker: str = "toss", order_type: str = "MARKET", lot_size: Decimal = Decimal("1")) -> PortfolioRevalidation:
        """Rebuild intent and risk approval from the latest account/market state."""
        symbol = str(row.get("symbol", "")).strip()
        if not symbol:
            raise ValueError("portfolio row symbol is required")
        raw_latest = latest_prices.get(symbol)
        if raw_latest is None:
            raise ValueError(f"missing latest price for target symbol: {symbol}")
        latest_price = Decimal(str(raw_latest))
        if latest_price <= 0:
            raise ValueError(f"latest price must be positive: {symbol}")
        snapshot = self.build_portfolio_risk_context(account, latest_prices, markets=markets, target_symbol=symbol)
        latest_row = dict(row)
        latest_row["close"] = str(latest_price)
        intent = self.intent_from_portfolio_row(latest_row, account_value=snapshot.context.account_value, current_quantity=account.positions.get(symbol, Decimal("0")), broker=broker, order_type=order_type, lot_size=lot_size)
        if intent is None:
            return PortfolioRevalidation(snapshot=snapshot, intent=None, preview=None)
        preview = self.preview(intent, latest_price, portfolio_context=snapshot.context)
        return PortfolioRevalidation(snapshot=snapshot, intent=intent, preview=preview)

    def submit_portfolio_row_revalidated(self, row: dict[str, Any], *, account: PaperAccount, latest_prices: Mapping[str, Decimal], markets: Mapping[str, str] | None = None, broker: str = "toss", order_type: str = "MARKET", lot_size: Decimal = Decimal("1"), approval_id: str | None = None, recommendation_run_id: str | None = None, portfolio_rank: int | None = None, run_manifest_id: str | None = None) -> Fill | OrderResult | None:
        """Revalidate immediately before submission; never reuse a stale preview."""
        result = self.revalidate_portfolio_row(row, account=account, latest_prices=latest_prices, markets=markets, broker=broker, order_type=order_type, lot_size=lot_size)
        if result.intent is None:
            return None
        target_weight = Decimal(str(row["target_weight"])) if "target_weight" in row else None
        return self.submit(
            result.intent,
            latest_prices[result.intent.symbol],
            approval_id=approval_id,
            portfolio_context=result.snapshot.context,
            recommendation_run_id=recommendation_run_id,
            portfolio_rank=portfolio_rank,
            target_weight=target_weight,
            run_manifest_id=run_manifest_id,
        )

    def to_paper_order(self, intent: OrderIntent) -> PaperOrderRequest:
        client_id = intent.client_order_id or f"paper-{uuid4().hex[:16]}"
        return PaperOrderRequest(intent.symbol, intent.normalized_side(), intent.quantity, intent.normalized_order_type(), intent.price, client_id)

    def to_broker_order(self, intent: OrderIntent) -> BrokerOrderRequest:
        return BrokerOrderRequest(symbol=intent.symbol, side=intent.normalized_side().value, quantity=intent.quantity, order_type=intent.normalized_order_type().value, price=intent.price)

    def _estimate_notional(self, intent: OrderIntent, reference_price: Decimal) -> Decimal:
        return intent.quantity * (intent.price if intent.price is not None else reference_price)

    def _assess_risk(self, intent: OrderIntent, reference_price: Decimal, portfolio_context: PortfolioRiskContext | None = None) -> RiskAssessment:
        order = self.to_paper_order(intent)
        try:
            if portfolio_context is None:
                self.risk.approve(order, reference_price)
            else:
                self.risk.approve_portfolio(order, reference_price, portfolio_context)
            return RiskAssessment(True, "PASS")
        except (PermissionError, ValueError) as exc:
            return RiskAssessment(False, "REJECT", (str(exc),))

    def preview(self, intent: OrderIntent, reference_price: Decimal, *, portfolio_context: PortfolioRiskContext | None = None) -> OrderPreview:
        if intent.quantity <= 0:
            raise ValueError("quantity must be positive")
        if reference_price <= 0 and intent.price is None:
            raise ValueError("reference_price or limit price is required")
        px = reference_price if reference_price > 0 else (intent.price or Decimal("0"))
        mode = self.controller.get_current_mode()
        risk = self._assess_risk(intent, px, portfolio_context)
        requires_approval = mode is ExecutionEnvironmentMode.REAL_LIVE
        preview_id = f"prv-{uuid4().hex[:16]}"
        message = ("REAL_LIVE requires approval_id; call submit with order approval." if requires_approval else "Risk passed; submit without approval_id on paper/virtual path.") if risk.approved else "Risk rejected; submit will fail until limits are adjusted."
        preview = OrderPreview(intent, self._estimate_notional(intent, px), self.currency, risk, requires_approval, preview_id, mode.value, message)
        self._previews[preview_id] = preview
        return preview

    def _resolve_live_secret(self, intent: OrderIntent, *, capability: str = "order.create") -> str:
        if self.secret_broker is None:
            raise PermissionError("SecretBroker is required for REAL_LIVE submit")
        secret_id = self.broker_secret_ids.get(intent.broker)
        if not secret_id:
            raise PermissionError(f"no secret mapping for broker: {intent.broker}")
        return self.secret_broker.resolve(secret_id=secret_id, mode=ExecutionEnvironmentMode.REAL_LIVE.value, capability=capability)

    def _adapter_for(self, broker: str):
        if self.broker_router is None:
            raise PermissionError("BrokerRouter is not configured")
        adapter = self.broker_router.adapters.get(broker)
        if adapter is None:
            raise PermissionError(f"broker adapter is not configured: {broker}")
        return adapter

    def _inject_credentials(self, intent: OrderIntent, *, capability: str = "order.create") -> object:
        material = self._resolve_live_secret(intent, capability=capability)
        adapter = self._adapter_for(intent.broker)
        apply = getattr(adapter, "apply_secret_material", None)
        if apply is not None:
            apply(material)
        return adapter

    def _submit_live(self, intent: OrderIntent, *, approval_id: str | None) -> OrderResult:
        if self.broker_router is None:
            raise PermissionError("BrokerRouter is not configured")
        if self.order_approval_gate is None or approval_id is None:
            raise PermissionError("explicit live approval_id is required")
        self.order_approval_gate.require(approval_id)
        adapter = self._inject_credentials(intent)
        try:
            return self.broker_router.submit(ExecutionEnvironmentMode.REAL_LIVE.value, intent.broker, self.to_broker_order(intent), approval_id)
        finally:
            clear = getattr(adapter, "clear_secret_material", None)
            if clear is not None:
                clear()

    def _audit_submission(self, intent: OrderIntent, reference_price: Decimal, risk: RiskAssessment, *, portfolio_context: PortfolioRiskContext | None, recommendation_run_id: str | None, portfolio_rank: int | None, target_weight: Decimal | None, preview_id: str | None, run_manifest_id: str | None) -> ExecutionAuditRecord | None:
        if self.audit_trail is None:
            return None
        return self.audit_trail.create_submission(intent=intent, reference_price=reference_price, risk=risk, portfolio_context=portfolio_context, recommendation_run_id=recommendation_run_id, portfolio_rank=portfolio_rank, target_weight=target_weight, preview_id=preview_id, broker=intent.broker, run_manifest_id=run_manifest_id)

    def submit(self, intent: OrderIntent, reference_price: Decimal, *, approval_id: str | None = None, preview_id: str | None = None, portfolio_context: PortfolioRiskContext | None = None, recommendation_run_id: str | None = None, portfolio_rank: int | None = None, target_weight: Decimal | None = None, run_manifest_id: str | None = None) -> Fill | OrderResult:
        mode = self.controller.get_current_mode()
        if preview_id is not None:
            stored = self._previews.get(preview_id)
            if stored is None:
                raise ValueError("unknown preview_id")
            if not stored.risk.approved:
                raise PermissionError("preview risk was not approved")
            intent = stored.intent
        if not intent.client_order_id:
            intent = replace(intent, client_order_id=f"paper-{uuid4().hex[:16]}")
        risk = self._assess_risk(intent, reference_price, portfolio_context)
        audit = self._audit_submission(intent, reference_price, risk, portfolio_context=portfolio_context, recommendation_run_id=recommendation_run_id, portfolio_rank=portfolio_rank, target_weight=target_weight, preview_id=preview_id, run_manifest_id=run_manifest_id)
        if not risk.approved:
            raise PermissionError("; ".join(risk.violations) or "risk rejected")
        if mode is ExecutionEnvironmentMode.REAL_LIVE:
            result = self._submit_live(intent, approval_id=approval_id)
            if audit is not None:
                self.audit_trail.record_fill(audit, Fill(result.order_id, intent.symbol, intent.normalized_side(), Decimal("0"), reference_price, Decimal("0"), Decimal("0"), "ACCEPTED" if result.accepted else "REJECTED"))
            return result
        result = self.gateway.execute(self.to_paper_order(intent), reference_price)
        if audit is not None:
            self.audit_trail.record_fill(audit, result)
        return result

    def cancel(self, *, broker: str, order_id: str, approval_id: str | None = None, symbol: str | None = None) -> bool:
        mode = self.controller.get_current_mode()
        if mode is not ExecutionEnvironmentMode.REAL_LIVE:
            raise PermissionError("cancel via broker is only available in REAL_LIVE")
        if self.broker_router is None:
            raise PermissionError("BrokerRouter is not configured")
        if self.order_approval_gate is None or approval_id is None:
            raise PermissionError("explicit live approval_id is required")
        self.order_approval_gate.require(approval_id)
        intent = OrderIntent(symbol=(symbol or "-"), side="BUY", quantity=Decimal("1"), broker=broker)
        adapter = self._inject_credentials(intent, capability="order.cancel")
        try:
            return self.broker_router.cancel(mode.value, broker, order_id, approval_id, symbol=symbol)
        finally:
            clear = getattr(adapter, "clear_secret_material", None)
            if clear is not None:
                clear()

    def snapshot(self) -> dict[str, Any]:
        mode = self.controller.get_current_mode()
        return {"mode": mode.value, "has_broker_router": self.broker_router is not None, "has_secret_broker": self.secret_broker is not None, "has_order_approval_gate": self.order_approval_gate is not None, "has_audit_trail": self.audit_trail is not None, "open_previews": len(self._previews)}
