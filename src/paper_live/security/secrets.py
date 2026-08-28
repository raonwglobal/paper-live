from __future__ import annotations
import os
from dataclasses import dataclass


class SecretAccessDenied(PermissionError):
    """Raised when a required broker credential is unavailable."""


# Backward-compatible public name used by existing callers/tests.
CredentialError = SecretAccessDenied


@dataclass(frozen=True)
class BrokerCredentials:
    client_id: str
    client_secret: str
    account_seq: str


@dataclass(frozen=True)
class CredentialProvider:
    """Host-only credential loader; plugin environments never receive secrets."""

    def _require(self, name: str) -> str:
        value = os.getenv(name)
        if not value:
            raise CredentialError(f"missing required secret: {name}")
        return value

    def load_toss(self) -> BrokerCredentials:
        return BrokerCredentials(
            client_id=self._require("TOSS_CLIENT_ID"),
            client_secret=self._require("TOSS_CLIENT_SECRET"),
            account_seq=self._require("TOSS_ACCOUNT_SEQ"),
        )

    def plugin_env(self) -> dict[str, str]:
        return {}


@dataclass(frozen=True)
class BrokerSecretProvider:
    """Compatibility facade for host-only secret access."""

    def require(self, name: str) -> str:
        value = os.getenv(name)
        if not value:
            raise SecretAccessDenied(f"missing required secret: {name}")
        return value

    def plugin_env(self) -> dict[str, str]:
        return {}
