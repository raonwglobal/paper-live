from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Protocol


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

    def __post_init__(self) -> None:
        if len({item.stage for item in self.stages}) != len(self.stages):
            raise ValueError("run manifest stages must be unique")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def checksum_sha256(self) -> str:
        payload = json.dumps(
            self.as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def stage(self, name: str) -> RunArtifact | None:
        return next((item for item in self.stages if item.stage == name), None)

    def with_stage(self, artifact: RunArtifact) -> RunManifestV3:
        if self.stage(artifact.stage) is None:
            raise KeyError(f"unknown run manifest stage: {artifact.stage}")
        stages = tuple(artifact if item.stage == artifact.stage else item for item in self.stages)
        return replace(self, stages=stages)

    def with_status(self, status: str) -> RunManifestV3:
        return replace(self, status=status)


@dataclass(frozen=True)
class RunFinalizationResult:
    """Final persisted state of one completed or failed runtime run."""

    run_id: str
    status: str
    manifest_checksum_sha256: str
    manifest_uri: str | None
    audit_uri: str | None


def build_run_manifest_v3(
    *,
    run_id: str,
    status: str,
    decision_time: str,
    ingestion: RunArtifact,
    features: RunArtifact,
    recommendations: RunArtifact,
    portfolio: RunArtifact,
    risk: RunArtifact,
    execution_audit: RunArtifact,
    fill: RunArtifact,
    pnl: RunArtifact,
    reflection: RunArtifact,
) -> RunManifestV3:
    stages = (ingestion, features, recommendations, portfolio, risk, execution_audit, fill, pnl, reflection)
    if len({item.stage for item in stages}) != len(stages):
        raise ValueError("run manifest stages must be unique")
    return RunManifestV3(run_id=run_id, status=status, decision_time=decision_time, stages=stages)


@dataclass
class RunManifestTracker:
    """Runtime registry that persists the same run_id as execution events arrive."""

    writer: RunManifestWriter | None = None
    manifests: dict[str, RunManifestV3] = field(default_factory=dict)

    def register(self, manifest: RunManifestV3, *, persist: bool = True) -> RunManifestV3:
        self.manifests[manifest.run_id] = manifest
        if persist:
            self._persist(manifest)
        return manifest

    def get(self, run_id: str) -> RunManifestV3 | None:
        return self.manifests.get(run_id)

    def bind_stage(self, run_id: str, artifact: RunArtifact, *, persist: bool = True) -> RunManifestV3:
        manifest = self.manifests.get(run_id)
        if manifest is None:
            raise KeyError(run_id)
        updated = manifest.with_stage(artifact)
        self.manifests[run_id] = updated
        if persist:
            self._persist(updated)
        return updated

    def transition(self, run_id: str, status: str, *, persist: bool = True) -> RunManifestV3:
        manifest = self.manifests.get(run_id)
        if manifest is None:
            raise KeyError(run_id)
        updated = manifest.with_status(status)
        self.manifests[run_id] = updated
        if persist:
            self._persist(updated)
        return updated

    def finalize(
        self,
        run_id: str,
        *,
        status: str = "completed",
        audit_uri: str | None = None,
        persist: bool = True,
    ) -> RunFinalizationResult:
        manifest = self.manifests.get(run_id)
        if manifest is None:
            raise KeyError(run_id)
        updated = manifest.with_status(status)
        self.manifests[run_id] = updated
        manifest_uri = self._persist(updated) if persist else None
        return RunFinalizationResult(
            run_id=run_id,
            status=status,
            manifest_checksum_sha256=updated.checksum_sha256,
            manifest_uri=manifest_uri,
            audit_uri=audit_uri,
        )

    def _persist(self, manifest: RunManifestV3) -> str | None:
        if self.writer is None:
            return None
        return self.writer.write_run_manifest(manifest.run_id, manifest.as_dict())


def persist_run_manifest(writer: RunManifestWriter, manifest: RunManifestV3) -> str:
    return writer.write_run_manifest(manifest.run_id, manifest.as_dict())
