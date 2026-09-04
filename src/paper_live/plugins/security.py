from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from .manifest import PluginManifest


class PluginSecurityError(ValueError):
    pass


@dataclass(frozen=True)
class SecurityPolicy:
    allowed_hosts: tuple[str, ...] = ("github.com", "raw.githubusercontent.com")
    allow_shell: bool = False
    allow_live: bool = False


class PluginSecurityValidator:
    def __init__(self, policy: SecurityPolicy | None = None):
        self.policy = policy or SecurityPolicy()

    def validate_source(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in self.policy.allowed_hosts:
            raise PluginSecurityError("plugin source must use an allowed HTTPS GitHub host")
        if parsed.username or parsed.password:
            raise PluginSecurityError("credential-bearing repository URLs are forbidden")

    def validate_manifest(self, manifest: PluginManifest) -> None:
        permissions = manifest.permissions
        if permissions.shell and not self.policy.allow_shell:
            raise PluginSecurityError("shell permission is disabled")
        if "REAL_LIVE" in permissions.allowed_modes and not self.policy.allow_live:
            raise PluginSecurityError("plugins cannot self-grant REAL_LIVE access")
        if any(not host or "*" in host for host in permissions.network_allow):
            raise PluginSecurityError("network permissions must use explicit hosts")
        if any(not name or name.startswith("/") for name in permissions.secret_allow):
            raise PluginSecurityError("secret permissions must use named allow-list entries")
