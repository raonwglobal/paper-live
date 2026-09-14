from paper_live.run_manifest import RunArtifact, build_run_manifest_v3


def test_run_manifest_v3_preserves_stage_order_and_checksum():
    stages = {
        name: RunArtifact(stage=name, artifact_id=f"{name}-1", status="completed")
        for name in (
            "ingestion", "features", "recommendations", "portfolio", "risk",
            "execution_audit", "fill", "pnl", "reflection",
        )
    }
    manifest = build_run_manifest_v3(
        run_id="run-1", status="completed", decision_time="2026-08-28T19:00:00+09:00",
        **stages,
    )
    assert [item.stage for item in manifest.stages] == list(stages)
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
