from __future__ import annotations

from dataclasses import dataclass
import os
import secrets


class CredentialError(RuntimeError):
    pass


@dataclass(frozen=True)
class BrokerCredentials:
    access_token: str
    account_id: str


class CredentialProvider:
    """Credentials are loaded from process environment only; never from source files."""

    def load_toss(self) -> BrokerCredentials:
        token = os.getenv("TOSS_API_TOKEN", "")
        account = os.getenv("TOSS_ACCOUNT_SEQ", "")
        if not token or not account:
            raise CredentialError("TOSS_API_TOKEN and TOSS_ACCOUNT_SEQ are required")
        return BrokerCredentials(token, account)

    def load_kb(self) -> BrokerCredentials:
        token = os.getenv("KB_API_TOKEN", "")
        account = os.getenv("KB_ACCOUNT_ID", "")
        if not token or not account:
            raise CredentialError("KB_API_TOKEN and KB_ACCOUNT_ID are required")
        return BrokerCredentials(token, account)


class LiveApprovalGate:
    """Two-party style in-process approval gate; no automatic KPI promotion."""

    def __init__(self) -> None:
        self._approvals: set[str] = set()
        self._nonce = secrets.token_hex(16)

    @property
    def nonce(self) -> str:
        return self._nonce

    def approve(self, approver: str, nonce: str) -> None:
        if not approver or not nonce or not secrets.compare_digest(nonce, self._nonce):
            raise PermissionError("invalid live approval")
        self._approvals.add(approver)

    def approved(self, minimum: int = 1) -> bool:
        return len(self._approvals) >= minimum
