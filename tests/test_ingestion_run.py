from datetime import date

from paper_live.data_lake import LocalDriveMirror
from paper_live.ingestion_run import FailureQueue, IngestionFailure, IngestionRunLedger, build_manifest


def failure(symbol: str, *, retryable: bool = True, attempts: int = 1) -> IngestionFailure:
    return IngestionFailure(market="KRX", symbol=symbol, start_date="2026-08-28", end_date="2026-08-28",
                            error_type="TimeoutError", error_message="temporary failure", attempts=attempts,
                            retryable=retryable)


def test_failure_queue_is_deterministic_and_deduplicated():
    queue = FailureQueue([failure("005930"), failure("000660", attempts=2), failure("005930", attempts=3)])
    items = queue.retryable()
    assert [item.symbol for item in items] == ["000660", "005930"]
    assert items[-1].attempts == 3


def test_run_manifest_reports_partial_failure():
    queue = FailureQueue([failure("005930"), failure("000660", retryable=False)])
    manifest = build_manifest(run_id="abc", started_at="2026-08-28T18:00:00+09:00", market="KRX",
                              start_date=date(2026, 8, 28), end_date=date(2026, 8, 28), requested_symbols=3,
                              succeeded_symbols=1, rows_collected=10, failures=queue,
                              finished_at="2026-08-28T18:05:00+09:00")
    assert manifest.status == "completed_with_failures"
    assert manifest.failed_symbols == 2
    assert manifest.retryable_failures == 1
    assert manifest.non_retryable_failures == 1


def test_run_ledger_persists_manifest_and_failure_queue(tmp_path):
    ledger = IngestionRunLedger(LocalDriveMirror(tmp_path), folder_id="datasets")
    queue = FailureQueue([failure("005930")])
    manifest = build_manifest(run_id="abc123", started_at="2026-08-28T18:00:00+09:00", market="KRX",
                              start_date=date(2026, 8, 28), end_date=date(2026, 8, 28), requested_symbols=2,
                              succeeded_symbols=1, rows_collected=1, failures=queue)
    manifest_id, failure_id = ledger.write(manifest, queue)
    assert manifest_id.endswith("manifest.json")
    assert failure_id.endswith("failures.jsonl")
    assert (tmp_path / "datasets" / "runs" / "KRX" / "abc123" / "manifest.json").exists()
    assert (tmp_path / "datasets" / "runs" / "KRX" / "abc123" / "failures.jsonl").exists()
