from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .order_lifecycle import OrderLifecycle


@dataclass(frozen=True)
class ReconciliationIssue:
    client_order_id: str
    kind: str
    expected: str
    observed: str


class OrderReconciler:
    """Compare local order state with broker/paper observations without mutating execution state."""

    def __init__(self, lifecycle: OrderLifecycle):
        self.lifecycle = lifecycle

    def compare(self, observations: list[dict]) -> list[ReconciliationIssue]:
        issues: list[ReconciliationIssue] = []
        for observed in observations:
            oid = str(observed["client_order_id"])
            local = self.lifecycle.get(oid)
            if local is None:
                issues.append(ReconciliationIssue(oid, "MISSING_LOCAL", "known order", "unknown"))
                continue
            status = str(observed.get("status", ""))
            filled = Decimal(str(observed.get("filled_quantity", "0")))
            if status != local.status.value:
                issues.append(ReconciliationIssue(oid, "STATUS_DRIFT", local.status.value, status))
            if filled != local.filled_quantity:
                issues.append(ReconciliationIssue(oid, "FILL_DRIFT", str(local.filled_quantity), str(filled)))
        return issues
