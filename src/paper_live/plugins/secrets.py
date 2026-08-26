from __future__ import annotations

class SecretAccessDenied(PermissionError):
    pass

class SecretBroker:
    """Resolves only explicitly allowed secret names; never exposes the host env."""
    def __init__(self, secrets: dict[str, str] | None = None):
        self._secrets = dict(secrets or {})

    def resolve(self, name: str, allowed: set[str]) -> str:
        if name not in allowed:
            raise SecretAccessDenied(f"secret access denied: {name}")
        if name not in self._secrets:
            raise KeyError(name)
        return self._secrets[name]
