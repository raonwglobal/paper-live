from __future__ import annotations

from dataclasses import dataclass


class SandboxViolation(PermissionError):
    pass


@dataclass(frozen=True)
class SandboxPolicy:
    network_hosts: tuple[str, ...] = ()
    readable_paths: tuple[str, ...] = ()
    writable_paths: tuple[str, ...] = ()
    allow_shell: bool = False
    max_cpu_seconds: int = 10
    max_memory_mb: int = 256
    timeout_seconds: int = 30


class PluginSandbox:
    """Policy boundary for untrusted plugins.

    This object deliberately does not execute arbitrary code. A production
    executor must enforce this policy at the OS/container boundary.
    """

    def __init__(self, policy: SandboxPolicy | None = None):
        self.policy = policy or SandboxPolicy()

    def check_network(self, host: str) -> None:
        if host not in self.policy.network_hosts:
            raise SandboxViolation(f"network access denied: {host}")

    def check_read(self, path: str) -> None:
        if not any(path == p or path.startswith(p.rstrip("/") + "/") for p in self.policy.readable_paths):
            raise SandboxViolation(f"read access denied: {path}")

    def check_write(self, path: str) -> None:
        if not any(path == p or path.startswith(p.rstrip("/") + "/") for p in self.policy.writable_paths):
            raise SandboxViolation(f"write access denied: {path}")

    def check_shell(self) -> None:
        if not self.policy.allow_shell:
            raise SandboxViolation("shell execution denied")
