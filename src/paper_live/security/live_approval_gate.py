from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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
        if not approved_by.strip() or not 1 <= ttl_seconds <= 3600:
            raise LiveApprovalDenied("valid approver and TTL are required")
        now = datetime.now(timezone.utc)
        approval = LiveApproval(secrets.token_urlsafe(18), approved_by.strip(), now + timedelta(seconds=ttl_seconds))
        self._approval = approval
        return approval

    def revoke(self) -> None:
        self._approval = None

    def require(self, approval_id: str) -> None:
        a = self._approval
        if a is None or a.approval_id != approval_id or datetime.now(timezone.utc) >= a.expires_at:
            raise LiveApprovalDenied("valid live approval is required")
