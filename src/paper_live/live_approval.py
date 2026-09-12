"""Environment promotion live-approval gate.

This gate controls whether `EnvironmentController` may enter `REAL_LIVE`.
It is intentionally simpler than the order-level gate in
`paper_live.security.live_approval_gate`, which issues short-lived
approval IDs for individual broker submits.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from .environment import EnvironmentTransitionError, ExecutionEnvironmentMode


@dataclass(frozen=True)
class LiveApproval:
    approved_by: str
    approved_at: datetime
    reason: str


class LiveApprovalGate:
    """Explicit human approval required before REAL_LIVE environment promotion."""

    def __init__(self):
        self._approval: LiveApproval | None = None

    def approve(self, operator: str, reason: str) -> LiveApproval:
        if not operator.strip() or not reason.strip():
            raise ValueError("operator and reason are required")
        self._approval = LiveApproval(operator, datetime.now(UTC), reason)
        return self._approval

    def revoke(self) -> None:
        self._approval = None

    def require(self, mode: ExecutionEnvironmentMode) -> None:
        if mode is ExecutionEnvironmentMode.REAL_LIVE and self._approval is None:
            raise EnvironmentTransitionError("REAL_LIVE requires explicit live approval")

    def approved(self) -> bool:
        return self._approval is not None
