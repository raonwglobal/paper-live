from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Protocol


class RunManifestWriter(Protocol):
    def write_run_manifest(self, run_id: str, manifest: dict[str, Any], *, folder_name: str = "runs") -> str: ...


@dataclass(frozen=True)
class RunArtifact:
    """A secret-free, reproducible reference to one pipeline artifact."""
    stage: str
    artifact_id: str | None = None
    dataset: str | None = None
    row_count: int | None = None
    checksum_sha256: str | None = None
    status: str = "not_run"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RunManifestV3:
    """Canonical lineage manifest from ingestion through reflection."""
    run_id: str
    status: str
    decision_time: str
    stages: tuple[RunArtifact, ...]
    schema_version: str = "paper-live-run-v3"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def checksum_sha256(self) -> str:
        payload = json.dumps(self.as_dict(), ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), default=str).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def stage(self, name: str) -> RunArtifact | None:
        return next((item for item in self.stages if item.stage == name), None)


def build_run_manifest_v3(*, run_id: str, status: str, decision_time: str,
                          ingestion: RunArtifact, features: RunArtifact,
                          recommendations: RunArtifact, portfolio: RunArtifact,
                          risk: RunArtifact, execution_audit: RunArtifact,
                          fill: RunArtifact, pnl: RunArtifact,
                          reflection: RunArtifact) -> RunManifestV3:
    stages = (ingestion, features, recommendations, portfolio, risk,
              execution_audit, fill, pnl, reflection)
    if len({item.stage for item in stages}) != len(stages):
        raise ValueError("run manifest stages must be unique")
    return RunManifestV3(run_id=run_id, status=status, decision_time=decision_time, stages=stages)


def persist_run_manifest(writer: RunManifestWriter, manifest: RunManifestV3) -> str:
    return writer.write_run_manifest(manifest.run_id, manifest.as_dict())
