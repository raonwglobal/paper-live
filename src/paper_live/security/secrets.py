from __future__ import annotations
import os
from dataclasses import dataclass

class SecretAccessDenied(PermissionError):
    pass

@dataclass(frozen=True)
class BrokerSecretProvider:
    """Reads secrets only from the host process environment; never exposes them to plugins."""
    def require(self, name: str) -> str:
        value = os.getenv(name)
        if not value:
            raise SecretAccessDenied(f"missing required secret: {name}")
        return value

    def plugin_env(self) -> dict[str, str]:
        return {}
