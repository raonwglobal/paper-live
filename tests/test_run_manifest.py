from paper_live.run_manifest import RunArtifact, RunManifestTracker, build_run_manifest_v3


def _manifest():
    stages = {
        name: RunArtifact(stage=name, artifact_id=f"{name}-1", status="not_run")
        for name in (
            "ingestion", "features", "recommendations", "portfolio", "risk",
            "execution_audit", "fill", "pnl", "reflection",
        )
    }
    return build_run_manifest_v3(
        run_id="run-1", status="running", decision_time="2026-08-28T19:00:00+09:00", **stages,
    )


def test_run_manifest_v3_preserves_stage_order_and_checksum():
    manifest = _manifest()
    assert [item.stage for item in manifest.stages] == [
        "ingestion", "features", "recommendations", "portfolio", "risk",
        "execution_audit", "fill", "pnl", "reflection",
    ]
    assert manifest.schema_version == "paper-live-run-v3"
    assert len(manifest.checksum_sha256) == 64
    assert manifest.stage("execution_audit").artifact_id == "execution_audit-1"


def test_run_manifest_v3_rejects_duplicate_stages():
    common = RunArtifact(stage="same")
    try:
        build_run_manifest_v3(
            run_id="run-1", status="completed", decision_time="2026-08-28T19:00:00+09:00",
            ingestion=common, features=RunArtifact(stage="features"),
            recommendations=RunArtifact(stage="recommendations"), portfolio=RunArtifact(stage="portfolio"),
            risk=RunArtifact(stage="risk"), execution_audit=RunArtifact(stage="execution_audit"),
            fill=RunArtifact(stage="fill"), pnl=RunArtifact(stage="pnl"), reflection=RunArtifact(stage="reflection"),
        )
    except ValueError as exc:
        assert "unique" in str(exc)
    else:
        raise AssertionError("duplicate stages must be rejected")


class _Writer:
    def __init__(self):
        self.calls = []

    def write_run_manifest(self, run_id, manifest, *, folder_name="runs"):
        self.calls.append((run_id, manifest["status"], manifest["stages"]))
        return f"drive://{run_id}/{len(self.calls)}"


def test_tracker_persists_stage_updates_and_finalization():
    writer = _Writer()
    tracker = RunManifestTracker(writer=writer)
    tracker.register(_manifest())
    tracker.bind_stage("run-1", RunArtifact(stage="fill", artifact_id="fill-a", status="completed"))
    result = tracker.finalize("run-1", status="completed", audit_uri="drive://audit/run-1")

    assert result.run_id == "run-1"
    assert result.status == "completed"
    assert result.audit_uri == "drive://audit/run-1"
    assert len(result.manifest_checksum_sha256) == 64
    assert len(writer.calls) == 3
    final = tracker.get("run-1")
    assert final is not None
    assert final.status == "completed"
    assert final.stage("fill").artifact_id == "fill-a"


def test_tracker_rejects_unknown_run_or_stage():
    tracker = RunManifestTracker()
    try:
        tracker.bind_stage("missing", RunArtifact(stage="fill"))
    except KeyError as exc:
        assert str(exc).strip("'") == "missing"
    else:
        raise AssertionError("unknown run must fail closed")

    tracker.register(_manifest(), persist=False)
    try:
        tracker.bind_stage("run-1", RunArtifact(stage="unknown"))
    except KeyError as exc:
        assert "unknown" in str(exc)
    else:
        raise AssertionError("unknown stage must fail closed")
