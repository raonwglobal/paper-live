from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Mapping, Protocol

from .execution import Fill
from .pnl import PortfolioLedger, Side
from .reflection import TradeEpisode


class AuditArtifactWriter(Protocol):
    def upload(self, name: str, content: bytes, *, folder_id: str | None = None,
               mime_type: str = "application/octet-stream") -> str: ...

    def ensure_folder(self, name: str, *, parent_id: str | None = None) -> str: ...


@dataclass(frozen=True)
class ExecutionAuditRecord:
    """Immutable, secret-free linkage for one order/execution decision."""
    audit_id: str
    status: str
    created_at: str
    symbol: str
    side: str
    quantity: str
    reference_price: str
    recommendation_run_id: str | None = None
    portfolio_rank: int | None = None
    target_weight: str | None = None
    risk_approved: bool = False
    risk_level: str = ""
    risk_violations: tuple[str, ...] = ()
    account_value: str | None = None
    portfolio_notional: str | None = None
    market_notional: str | None = None
    market: str = ""
    client_order_id: str = ""
    preview_id: str | None = None
    broker: str = ""
    broker_order_id: str | None = None
    fill_quantity: str | None = None
    fill_price: str | None = None
    fee: str | None = None
    tax: str | None = None
    pnl: str | None = None
    pnl_reference: str | None = None
    reflection_episode_id: str | None = None
    run_manifest_id: str | None = None
    message: str = ""
    schema_version: str = "execution-audit-v1"


@dataclass
class ExecutionAuditTrail:
    """In-memory audit sink with optional Drive-compatible persistence."""
    records: list[ExecutionAuditRecord] = field(default_factory=list)
    writer: AuditArtifactWriter | None = None
    folder_id: str | None = None

    @staticmethod
    def _id(payload: Mapping[str, Any]) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        return "aud-" + hashlib.sha256(canonical).hexdigest()[:20]

    def append(self, record: ExecutionAuditRecord) -> ExecutionAuditRecord:
        if any(item.audit_id == record.audit_id for item in self.records):
            return record
        self.records.append(record)
        return record

    def create_submission(self, *, intent: Any, reference_price: Decimal, risk: Any,
                          portfolio_context: Any = None, recommendation_run_id: str | None = None,
                          portfolio_rank: int | None = None, target_weight: Decimal | None = None,
                          preview_id: str | None = None, broker: str = "",
                          run_manifest_id: str | None = None) -> ExecutionAuditRecord:
        payload = {"symbol": intent.symbol, "side": intent.side, "quantity": str(intent.quantity),
                   "client_order_id": intent.client_order_id, "recommendation_run_id": recommendation_run_id,
                   "portfolio_rank": portfolio_rank}
        context = portfolio_context
        record = ExecutionAuditRecord(
            audit_id=self._id(payload), status="SUBMITTED", created_at=datetime.now(UTC).isoformat(),
            symbol=intent.symbol, side=intent.side, quantity=str(intent.quantity), reference_price=str(reference_price),
            recommendation_run_id=recommendation_run_id, portfolio_rank=portfolio_rank,
            target_weight=None if target_weight is None else str(target_weight), risk_approved=bool(risk.approved),
            risk_level=str(risk.level), risk_violations=tuple(risk.violations),
            account_value=None if context is None else str(context.account_value),
            portfolio_notional=None if context is None else str(context.portfolio_notional),
            market_notional=None if context is None else str(context.market_notional),
            market="" if context is None else str(context.market), client_order_id=str(intent.client_order_id),
            preview_id=preview_id, broker=broker, run_manifest_id=run_manifest_id)
        return self.append(record)

    def record_result(self, submission: ExecutionAuditRecord, result: Any) -> ExecutionAuditRecord:
        values = {**asdict(submission), "status": str(getattr(result, "status", "ACCEPTED")),
                  "message": str(getattr(result, "message", ""))}
        if isinstance(result, Fill):
            values.update(fill_quantity=str(result.quantity), fill_price=str(result.price),
                          fee=str(result.fee), tax=str(result.tax), broker_order_id=result.order_id)
        else:
            values["broker_order_id"] = str(getattr(result, "order_id", "")) or None
        updated = ExecutionAuditRecord(**values)
        self.records[:] = [r for r in self.records if r.audit_id != submission.audit_id]
        return self.append(updated)

    def record_fill(self, submission: ExecutionAuditRecord, fill: Fill) -> ExecutionAuditRecord:
        return self.record_result(submission, fill)

    def record_pnl(self, audit_id: str, pnl: Decimal, *, pnl_reference: str) -> ExecutionAuditRecord:
        record = self.get(audit_id)
        if record is None:
            raise KeyError(audit_id)
        updated = ExecutionAuditRecord(**{**asdict(record), "pnl": str(pnl), "pnl_reference": pnl_reference})
        self.records[:] = [r for r in self.records if r.audit_id != audit_id]
        return self.append(updated)

    def record_reflection(self, audit_id: str, episode: TradeEpisode) -> ExecutionAuditRecord:
        record = self.get(audit_id)
        if record is None:
            raise KeyError(audit_id)
        updated = ExecutionAuditRecord(**{**asdict(record), "reflection_episode_id": episode.episode_id})
        self.records[:] = [r for r in self.records if r.audit_id != audit_id]
        return self.append(updated)

    def reconcile_fill_pnl(self, audit_id: str, ledger: PortfolioLedger, *, mark_price: Decimal) -> ExecutionAuditRecord:
        record = self.get(audit_id)
        if record is None or record.fill_quantity is None or record.fill_price is None:
            raise ValueError("audit record does not contain a fill")
        ledger.apply_fill(record.symbol, Side(record.side), Decimal(record.fill_quantity), Decimal(record.fill_price))
        pnl = ledger.total_pnl(record.symbol, mark_price)
        return self.record_pnl(audit_id, pnl, pnl_reference=f"ledger:{record.symbol}")

    def get(self, audit_id: str) -> ExecutionAuditRecord | None:
        return next((record for record in self.records if record.audit_id == audit_id), None)

    def to_jsonl(self) -> bytes:
        return b"".join(json.dumps(asdict(record), ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":")).encode("utf-8") + b"\n" for record in self.records)

    def persist(self, *, run_id: str, name: str = "execution-audit.jsonl") -> str | None:
        """Write an immutable run-scoped audit artifact when a writer is configured."""
        if self.writer is None:
            return None
        target = self.folder_id
        ensure_folder = getattr(self.writer, "ensure_folder", None)
        if callable(ensure_folder):
            target = ensure_folder("execution-audit", parent_id=target)
            target = ensure_folder(run_id, parent_id=target)
        return self.writer.upload(name, self.to_jsonl(), folder_id=target, mime_type="application/x-ndjson")
