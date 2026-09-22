from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

from .execution import Fill
from .pnl import PortfolioLedger, Side
from .reflection import TradeEpisode
from .run_manifest import RunArtifact, RunManifestTracker


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
    manifest_tracker: RunManifestTracker | None = None

    @staticmethod
    def _id(payload: Mapping[str, Any]) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        return "aud-" + hashlib.sha256(canonical).hexdigest()[:20]

    def append(self, record: ExecutionAuditRecord) -> ExecutionAuditRecord:
        if any(item.audit_id == record.audit_id for item in self.records):
            return record
        self.records.append(record)
        return record

    def _bind(self, record: ExecutionAuditRecord, stage: str, *, status: str,
              artifact_id: str | None = None, metadata: Mapping[str, Any] | None = None) -> None:
        run_id = record.run_manifest_id
        if self.manifest_tracker is None or not run_id:
            return
        self.manifest_tracker.bind_stage(
            run_id,
            RunArtifact(
                stage=stage,
                artifact_id=artifact_id or record.audit_id,
                status=status,
                metadata={"audit_id": record.audit_id, **dict(metadata or {})},
            ),
        )

    def record_preflight(\n        self,\n        rows: list[dict[str, Any]] | tuple[dict[str, Any], ...],\n        result: Any,\n        *,\n        run_manifest_id: str | None = None,\n    ) -> tuple[ExecutionAuditRecord, ...]:\n        \"\"\"Record batch preflight decisions without creating or submitting orders.\"\"\"\n        approved_by_symbol = {\n            item.intent.symbol: item for item in result.approved if item.intent is not None\n        }\n        rejected_by_symbol = {str(row.get(\"symbol\", \"\")).strip(): reason for row, reason in result.rejected}\n        records: list[ExecutionAuditRecord] = []\n        for row in rows:\n            if not bool(row.get(\"portfolio_selected\")):\n                continue\n            symbol = str(row.get(\"symbol\", \"\")).strip()\n            if not symbol:\n                continue\n            rank_value = row.get(\"portfolio_rank\", row.get(\"rank\"))\n            rank = int(rank_value) if rank_value is not None else None\n            target_weight = row.get(\"target_weight\")\n            approved = approved_by_symbol.get(symbol)\n            reason = rejected_by_symbol.get(symbol)\n            if approved is not None:\n                snapshot = approved.snapshot\n                intent = approved.intent\n                status = \"PREFLIGHT_APPROVED\"\n                quantity = str(intent.quantity)\n                reference_price = str(intent.price or row.get(\"close\", \"0\"))\n                risk_violations: tuple[str, ...] = ()\n                risk_level = \"PASS\"\n                account_value = str(snapshot.context.account_value)\n                portfolio_notional = str(snapshot.context.portfolio_notional)\n                market_notional = str(snapshot.context.market_notional)\n                market = str(snapshot.context.market)\n                client_order_id = str(intent.client_order_id)\n                broker = str(intent.broker)\n            else:\n                status = \"PREFLIGHT_REJECTED\"\n                quantity = \"0\"\n                reference_price = str(row.get(\"close\", row.get(\"price\", \"0\")))\n                risk_violations = (reason or \"preflight rejected\",)\n                risk_level = \"REJECT\"\n                account_value = portfolio_notional = market_notional = None\n                market = str(row.get(\"market\", \"\"))\n                client_order_id = broker = \"\"\n            payload = {\n                \"run_manifest_id\": run_manifest_id, \"symbol\": symbol, \"portfolio_rank\": rank,\n                \"target_weight\": None if target_weight is None else str(target_weight),\n                \"status\": status, \"quantity\": quantity, \"reference_price\": reference_price,\n            }\n            record = ExecutionAuditRecord(\n                audit_id=\"pfa-\" + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(\",\", \":\")).encode()).hexdigest()[:20],\n                status=status, created_at=datetime.now(UTC).isoformat(), symbol=symbol,\n                side=str(row.get(\"side\", \"\")), quantity=quantity, reference_price=reference_price,\n                portfolio_rank=rank, target_weight=None if target_weight is None else str(target_weight),\n                risk_approved=approved is not None, risk_level=risk_level, risk_violations=risk_violations,\n                account_value=account_value, portfolio_notional=portfolio_notional, market_notional=market_notional,\n                market=market, client_order_id=client_order_id, broker=broker, run_manifest_id=run_manifest_id,\n                message=reason or \"preflight approved; no order submitted\",\n            )\n            records.append(self.append(record))\n        if run_manifest_id and self.manifest_tracker is not None:\n            canonical = json.dumps([asdict(item) for item in records], ensure_ascii=False, sort_keys=True, separators=(\",\", \":\")).encode()\n            checksum = hashlib.sha256(canonical).hexdigest()\n            self.manifest_tracker.bind_stage(\n                run_manifest_id,\n                RunArtifact(\n                    stage=\"risk\", artifact_id=\"preflight-\" + checksum[:20],\n                    row_count=len(records), status=\"completed\" if not result.rejected else \"rejected\",\n                    checksum_sha256=checksum,\n                    metadata={\n                        \"preflight_required\": True, \"rows_checked\": result.rows_checked,\n                        \"approved_count\": len(result.approved), \"rejected_count\": len(result.rejected),\n                    },\n                ),\n            )\n        return tuple(records)\n\n    def create_submission(self, *, intent: Any, reference_price: Decimal, risk: Any,
                          portfolio_context: Any = None, recommendation_run_id: str | None = None,
                          portfolio_rank: int | None = None, target_weight: Decimal | None = None,
                          preview_id: str | None = None, broker: str = "",
                          run_manifest_id: str | None = None) -> ExecutionAuditRecord:
        payload = {"symbol": intent.symbol, "side": intent.side, "quantity": str(intent.quantity),
                   "client_order_id": intent.client_order_id, "recommendation_run_id": recommendation_run_id,
                   "portfolio_rank": portfolio_rank, "run_manifest_id": run_manifest_id}
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
        result = self.append(record)
        self._bind(result, "execution_audit", status=result.status)
        return result

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
        updated = self.append(updated)
        if isinstance(result, Fill):
            self._bind(updated, "fill", status=updated.status, artifact_id=result.order_id,
                       metadata={"quantity": str(result.quantity), "price": str(result.price)})
        else:
            self._bind(updated, "execution_audit", status=updated.status,
                       metadata={"broker_order_id": updated.broker_order_id})
        return updated

    def record_fill(self, submission: ExecutionAuditRecord, fill: Fill) -> ExecutionAuditRecord:
        """Record a real fill; preserve zero-quantity broker acknowledgements as non-fills."""
        if fill.quantity <= 0 and fill.status in {"ACCEPTED", "REJECTED"}:
            values = {
                **asdict(submission),
                "status": fill.status,
                "broker_order_id": fill.order_id or None,
                "message": "",
                "fill_quantity": None,
                "fill_price": None,
                "fee": None,
                "tax": None,
            }
            updated = ExecutionAuditRecord(**values)
            self.records[:] = [r for r in self.records if r.audit_id != submission.audit_id]
            updated = self.append(updated)
            self._bind(updated, "execution_audit", status=updated.status,
                       metadata={"broker_order_id": updated.broker_order_id})
            return updated
        return self.record_result(submission, fill)

    def record_pnl(self, audit_id: str, pnl: Decimal, *, pnl_reference: str) -> ExecutionAuditRecord:
        record = self.get(audit_id)
        if record is None:
            raise KeyError(audit_id)
        updated = ExecutionAuditRecord(**{**asdict(record), "pnl": str(pnl), "pnl_reference": pnl_reference})
        self.records[:] = [r for r in self.records if r.audit_id != audit_id]
        updated = self.append(updated)
        self._bind(updated, "pnl", status="COMPLETED", metadata={"pnl": str(pnl), "pnl_reference": pnl_reference})
        return updated

    def record_reflection(self, audit_id: str, episode: TradeEpisode) -> ExecutionAuditRecord:
        record = self.get(audit_id)
        if record is None:
            raise KeyError(audit_id)
        updated = ExecutionAuditRecord(**{**asdict(record), "reflection_episode_id": episode.episode_id})
        self.records[:] = [r for r in self.records if r.audit_id != audit_id]
        updated = self.append(updated)
        self._bind(updated, "reflection", status="COMPLETED", artifact_id=episode.episode_id)
        return updated

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
