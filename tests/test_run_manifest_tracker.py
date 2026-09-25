from paper_live.run_manifest import RunArtifact, RunManifestTracker, build_run_manifest_v3


class _Writer:
    def __init__(self):
        self.calls = []

    def write_run_manifest(self, run_id, manifest, *, folder_name="runs"):
        self.calls.append((run_id, manifest, folder_name))
        return f"file:{run_id}"


def _manifest():
    names = ("ingestion", "features", "recommendations", "portfolio", "risk", "execution_audit", "fill", "pnl", "reflection")
    return build_run_manifest_v3(
        run_id="run-runtime", status="RUNNING", decision_time="2026-09-15T00:00:00+00:00",
        **{name: RunArtifact(stage=name) for name in names},
    )


def test_runtime_tracker_persists_stage_updates_for_same_run_id():
    writer = _Writer()
    tracker = RunManifestTracker(writer=writer)
    tracker.register(_manifest())
    tracker.bind_stage("run-runtime", RunArtifact("execution_audit", artifact_id="aud-1", status="SUBMITTED"))
    tracker.transition("run-runtime", "COMPLETED")
    assert len(writer.calls) == 3
    assert writer.calls[-1][0] == "run-runtime"
    assert writer.calls[-1][1]["status"] == "COMPLETED"
    assert writer.calls[-1][1]["stages"][5]["artifact_id"] == "aud-1"
