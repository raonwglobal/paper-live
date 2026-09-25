from decimal import Decimal

from paper_live.environment import EnvironmentController
from paper_live.execution import ExecutionGateway, Fill, PaperAccount, VirtualMatchingEngine
from paper_live.execution_audit import ExecutionAuditTrail
from paper_live.reflection import TradeEpisode
from paper_live.risk import RiskGuardian, RiskLimits
from paper_live.run_manifest import RunArtifact, RunManifestTracker, build_run_manifest_v3
from paper_live.trade_facade import InternalTradeFacade


def _facade(audit: ExecutionAuditTrail):
    account = PaperAccount(Decimal("1000000"))
    controller = EnvironmentController()
    gateway = ExecutionGateway(controller, VirtualMatchingEngine(account, slippage_bps=Decimal("0")))
    facade = InternalTradeFacade(controller, RiskGuardian(controller, account, RiskLimits()), gateway, audit_trail=audit)
    return facade, account


def _manifest(run_id: str):
    return build_run_manifest_v3(
        run_id=run_id, status="RUNNING", decision_time="2026-09-15T00:00:00+00:00",
        ingestion=RunArtifact("ingestion", status="COMPLETED"), features=RunArtifact("features", status="COMPLETED"),
        recommendations=RunArtifact("recommendations", status="COMPLETED"), portfolio=RunArtifact("portfolio", status="COMPLETED"),
        risk=RunArtifact("risk", status="COMPLETED"), execution_audit=RunArtifact("execution_audit"),
        fill=RunArtifact("fill"), pnl=RunArtifact("pnl"), reflection=RunArtifact("reflection"),
    )


def test_paper_submission_links_recommendation_risk_and_fill():
    audit = ExecutionAuditTrail()
    facade, account = _facade(audit)
    row = {"symbol": "005930", "target_weight": "0.10", "close": "100"}
    result = facade.submit_portfolio_row_revalidated(row, account=account, latest_prices={"005930": Decimal("200")}, recommendation_run_id="rec-20260915", portfolio_rank=2, run_manifest_id="run-abc")
    assert isinstance(result, Fill)
    assert len(audit.records) == 1
    record = audit.records[0]
    assert record.status == "FILLED"
    assert record.recommendation_run_id == "rec-20260915"
    assert record.portfolio_rank == 2
    assert record.target_weight == "0.10"
    assert record.risk_approved is True
    assert record.account_value == "1000000"
    assert record.run_manifest_id == "run-abc"
    assert record.fill_quantity == "500"
    assert record.fill_price == "200"
    assert record.fee == "15.00"
    assert "secret" not in audit.to_jsonl().decode().lower()


def test_runtime_submission_fill_pnl_reflection_update_same_manifest():
    run_id = "run-runtime-1"
    tracker = RunManifestTracker()
    tracker.register(_manifest(run_id), persist=False)
    audit = ExecutionAuditTrail(manifest_tracker=tracker)
    facade, account = _facade(audit)
    intent = facade.intent_from_portfolio_row({"symbol": "AAA", "target_weight": "0.10", "close": "100"}, account_value=account.cash)
    assert intent is not None
    result = facade.submit(intent, Decimal("100"), run_manifest_id=run_id)
    assert isinstance(result, Fill)
    audit_id = audit.records[0].audit_id
    manifest = tracker.get(run_id)
    assert manifest is not None
    assert manifest.stage("execution_audit").artifact_id == audit_id
    assert manifest.stage("fill").artifact_id == result.order_id
    audit.record_pnl(audit_id, Decimal("123.45"), pnl_reference="ledger:AAA")
    episode = TradeEpisode("ep-runtime-1", "AAA", "BUY", "100", "101", "123.45", {"audit_id": audit_id, "run_id": run_id}, "POSITIVE", "2026-09-15T00:00:00+00:00")
    audit.record_reflection(audit_id, episode)
    manifest = tracker.get(run_id)
    assert manifest is not None
    assert manifest.stage("pnl").metadata["pnl"] == "123.45"
    assert manifest.stage("reflection").artifact_id == "ep-runtime-1"
    assert audit.get(audit_id).reflection_episode_id == "ep-runtime-1"


def test_audit_can_link_pnl_and_reflection_episode():
    audit = ExecutionAuditTrail()
    facade, account = _facade(audit)
    intent = facade.intent_from_portfolio_row({"symbol": "AAA", "target_weight": "0.10", "close": "100"}, account_value=account.cash)
    assert intent is not None
    result = facade.submit(intent, Decimal("100"))
    assert isinstance(result, Fill)
    record = audit.records[0]
    audit.record_pnl(record.audit_id, Decimal("123.45"), pnl_reference="ledger:AAA")
    episode = TradeEpisode("ep-1", "AAA", "BUY", "100", "101", "123.45", {"audit_id": record.audit_id}, "POSITIVE", "2026-09-15T00:00:00+00:00")
    audit.record_reflection(record.audit_id, episode)
    linked = audit.get(record.audit_id)
    assert linked is not None
    assert linked.pnl == "123.45"
    assert linked.pnl_reference == "ledger:AAA"
    assert linked.reflection_episode_id == "ep-1"


def test_rejected_risk_is_audited_before_submit_fails():
    audit = ExecutionAuditTrail()
    account = PaperAccount(Decimal("100000"))
    controller = EnvironmentController()
    gateway = ExecutionGateway(controller, VirtualMatchingEngine(account, slippage_bps=Decimal("0")))
    facade = InternalTradeFacade(controller, RiskGuardian(controller, account, RiskLimits(min_cash_reserve=Decimal("0.50"))), gateway, audit_trail=audit)
    try:
        facade.submit(facade.intent_from_portfolio_row({"symbol": "AAA", "target_weight": "0.80", "close": "100"}, account_value=account.cash), Decimal("100"), recommendation_run_id="rec-rejected")
    except PermissionError:
        pass
    assert len(audit.records) == 1
    assert audit.records[0].risk_approved is False
    assert audit.records[0].status == "SUBMITTED"
