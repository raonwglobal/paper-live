from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any

from .sandbox import SandboxPolicy, SandboxViolation


class ContainerExecutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ContainerSpec:
    image: str = "python:3.12-slim"
    timeout_seconds: int = 30
    memory_mb: int = 256
    cpu: float = 0.5


class DockerPluginExecutor:
    """Run a plugin entrypoint through a locked-down Docker process.

    The plugin receives one JSON request on stdin and must emit one JSON response.
    No host networking, privileged mode, host filesystem mounts, or shell are used.
    """

    def __init__(self, spec: ContainerSpec | None = None):
        self.spec = spec or ContainerSpec()

    def execute(
        self, plugin_root: str, entrypoint: str, request: dict[str, Any], policy: SandboxPolicy
    ) -> dict[str, Any]:
        if policy.allow_shell:
            raise SandboxViolation("shell execution is not supported by the plugin container")
        if policy.network_hosts:
            raise ContainerExecutionError(
                "network allow-list requires a dedicated proxy; direct container networking is disabled"
            )
        cmd = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            "64",
            "--memory",
            f"{self.spec.memory_mb}m",
            "--cpus",
            str(self.spec.cpu),
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=16m",
            "-v",
            f"{plugin_root}:/plugin:ro",
            self.spec.image,
            "python",
            f"/plugin/{entrypoint}",
        ]
        try:
            completed = subprocess.run(
                cmd,
                input=json.dumps(request),
                text=True,
                capture_output=True,
                timeout=self.spec.timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ContainerExecutionError("plugin container execution failed or timed out") from exc
        if completed.returncode != 0:
            raise ContainerExecutionError(completed.stderr[-2000:] or "plugin exited with failure")
        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ContainerExecutionError("plugin returned invalid JSON") from exc
        if not isinstance(result, dict):
            raise ContainerExecutionError("plugin response must be a JSON object")
        return result
