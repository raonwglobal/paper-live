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
    """Short-lived live-trading approval with a per-instance nonce."""
    def __init__(self):
        self._approval: LiveApproval | None = None
        self.nonce = secrets.token_urlsafe(24)

    def approve(self, approved_by: str, nonce: str | None = None, ttl_seconds: int = 300) -> LiveApproval:
        if not isinstance(approved_by, str) or not approved_by.strip():
            raise LiveApprovalDenied("valid approver and TTL are required")
        if nonce is not None and nonce != self.nonce:
            raise LiveApprovalDenied("valid approval nonce is required")
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or not 1 <= ttl_seconds <= 3600:
            raise LiveApprovalDenied("valid approver and TTL are required")
        now = datetime.now(timezone.utc)
        approval = LiveApproval(secrets.token_urlsafe(18), approved_by.strip(), now + timedelta(seconds=ttl_seconds))
        self._approval = approval
        return approval

    def approved(self) -> bool:
        a = self._approval
        return a is not None and datetime.now(timezone.utc) < a.expires_at

    def revoke(self) -> None:
        self._approval = None

    def require(self, approval_id: str) -> None:
        a = self._approval
        if a is None or a.approval_id != approval_id or datetime.now(timezone.utc) >= a.expires_at:
            raise LiveApprovalDenied("valid live approval is required")
