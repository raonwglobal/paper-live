from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class SecretAccessDenied(PermissionError):
    """Raised when a caller is not allowed to use a credential."""


class SecretStore(Protocol):
    def get(self, secret_id: str) -> str: ...


@dataclass(frozen=True)
class SecretPolicy:
    """Environment-aware capability policy. Secret values never enter agent state."""

    live_secret_ids: frozenset[str] = frozenset()

    def authorize(self, *, secret_id: str, mode: str, capability: str) -> None:
        if mode in {"PAPER_SANDBOX", "VIRTUAL_BACKTEST"} and secret_id in self.live_secret_ids:
            raise SecretAccessDenied(f"live credential denied in {mode}")
        if capability in {"order.create", "order.cancel"} and mode != "REAL_LIVE":
            raise SecretAccessDenied(f"live trading credential denied outside REAL_LIVE: {capability}")


class SecretBroker:
    """Single host-side boundary for credentials; agents/plugins receive no secret listing."""

    def __init__(self, store: SecretStore, policy: SecretPolicy | None = None):
        self._store = store
        self._policy = policy or SecretPolicy()

    def resolve(self, *, secret_id: str, mode: str, capability: str) -> str:
        self._policy.authorize(secret_id=secret_id, mode=mode, capability=capability)
        return self._store.get(secret_id)
