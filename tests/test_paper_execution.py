from decimal import Decimal

from paper_live.data_lake import GoogleDriveStorageAgent, LocalDriveMirror
from paper_live.environment import EnvironmentController, ExecutionEnvironmentMode
from paper_live.execution import ExecutionGateway, PaperAccount, VirtualMatchingEngine
from paper_live.execution_audit import ExecutionAuditTrail
from paper_live.paper_execution import PaperExecutionOrchestrator
from paper_live.reflection import EpisodicMemory, SelfReflectionWorker
from paper_live.risk import RiskGuardian
from paper_live.run_manifest import RunArtifact, RunManifestTracker, build_run_manifest_v3
from paper_live.trade_facade import InternalTradeFacade


def test_paper_execution_connects_preflight_fill_pnl_reflection(tmp_path):
    run_id = "run-paper-execution"
    tracker = RunManifestTracker()
    tracker.register(
        build_run_manifest_v3(
            run_id=run_id,
            status="running",
            decision_time="2026-09-22T09:00:00+00:00",
            ingestion=RunArtifact(stage="ingestion", status="completed"),
            features=RunArtifact(stage="features", status="completed"),
            recommendations=RunArtifact(stage="recommendations", status="completed"),
            portfolio=RunArtifact(stage="portfolio", status="completed"),
            risk=RunArtifact(stage="risk"),
            execution_audit=RunArtifact(stage="execution_audit"),
            fill=RunArtifact(stage="fill"),
            pnl=RunArtifact(stage="pnl"),
            reflection=RunArtifact(stage="reflection"),
        ),
        persist=False,
    )
    audit = ExecutionAuditTrail(manifest_tracker=tracker)
    controller = EnvironmentController(initial_mode=ExecutionEnvironmentMode.PAPER_SANDBOX)
    account = PaperAccount(cash=Decimal("10000"), positions={"A": Decimal("10")})
    facade = InternalTradeFacade(
        controller=controller,
        risk=RiskGuardian(controller, account),
        gateway=ExecutionGateway(controller, VirtualMatchingEngine(account)),
        audit_trail=audit,
    )
    reflection = SelfReflectionWorker(EpisodicMemory(tmp_path / "episodes.jsonl"))
    storage = GoogleDriveStorageAgent(LocalDriveMirror(tmp_path / "drive"))
    orchestrator = PaperExecutionOrchestrator(
        facade=facade,
        reflection_worker=reflection,
        audit_trail=audit,
        manifest_tracker=tracker,
        storage=storage,
    )

    rows = [{
        "symbol": "A",
        "target_weight": "0.20",
        "close": "100",
        "portfolio_selected": True,
        "rank": 1,
        "market": "KRX",
    }]
    result = orchestrator.execute(
        rows,
        account=account,
        latest_prices={"A": Decimal("100")},
        markets={"A": "KRX"},
        run_manifest_id=run_id,
        trade_date="2026-09-22",
    )

    assert result.preflight.all_approved
    assert len(result.fills) == 1
    assert result.fills[0].status == "FILLED"
    assert result.fills[0].quantity == Decimal("12")
    assert account.positions["A"] == Decimal("22")
    assert account.cash < Decimal("10000")
    assert len(result.pnl_audits) == 1
    assert len(result.reflection_episodes) == 1

    record = audit.get(result.pnl_audits[0])
    assert record is not None
    assert record.fill_quantity == "12"
    assert record.pnl is not None
    assert record.reflection_episode_id == result.reflection_episodes[0]

    manifest = tracker.get(run_id)
    assert manifest is not None
    assert manifest.stage("risk").status == "completed"
    assert manifest.stage("fill").status == "completed"
    assert manifest.stage("pnl").status == "COMPLETED"
    assert manifest.stage("reflection").status == "COMPLETED"
    assert (tmp_path / "drive" / "root" / "runs" / run_id / "execution" / "fills" / "trade_date=2026-09-22" / "fills.jsonl").exists()
    assert (tmp_path / "drive" / "root" / "runs" / run_id / "execution" / "pnl" / "trade_date=2026-09-22" / "pnl.jsonl").exists()
    assert (tmp_path / "drive" / "root" / "runs" / run_id / "execution" / "reflection" / "trade_date=2026-09-22" / "reflection.jsonl").exists()
