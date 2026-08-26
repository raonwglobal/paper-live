from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import secrets

class LiveApprovalDenied(PermissionError):
    pass

@dataclass(frozen=True)
class LiveApproval:
    approval_id: str
    approved_by: str
    expires_at: datetime

class LiveApprovalGate:
    def __init__(self):
        self._approval: LiveApproval | None = None

    def approve(self, approved_by: str, ttl_seconds: int = 300) -> LiveApproval:
        if not approved_by.strip():
            raise LiveApprovalDenied("approver is required")
        approval = LiveApproval(secrets.token_urlsafe(18), approved_by, datetime.now(timezone.utc).replace(microsecond=0))
        object.__setattr__(approval, "expires_at", datetime.fromtimestamp(approval.expires_at.timestamp() + ttl_seconds, tz=timezone.utc))
        self._approval = approval
        return approval

    def revoke(self) -> None:
        self._approval = None

    def require(self, approval_id: str) -> None:
        a = self._approval
        if a is None or a.approval_id != approval_id or datetime.now(timezone.utc) >= a.expires_at:
            raise LiveApprovalDenied("valid live approval is required")
