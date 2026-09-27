from __future__ import annotations

from contextlib import contextmanager
from datetime import date

import pytest

from paper_live.operations import OperationalDailyRunner

class FakeLock:
    def __init__(self): self.tokens: list[str] = []
    @contextmanager
    def acquire(self, token: str):
        self.tokens.append(token)
        yield

class FakeNotifier:
    def __init__(self): self.messages: list[str] = []
    def send(self, message: str) -> bool: self.messages.append(message); return True

class FakeJob:
    def __init__(self, result=None, error: Exception | None = None): self.result, self.error, self.calls = result, error, 0
    def run(self, **kwargs):
        self.calls += 1
        if self.error: raise self.error
        return self.result

class Manifest:
    run_id = "run-1"; status = "completed"; succeeded_symbols = 10; failed_symbols = 0
class Result:
    ingestion = type("Ingestion", (), {"manifest": Manifest()})()
    ranked = ({"symbol": "A"}, {"symbol": "B"})

def run(runner):
    return runner.run(start_date=date(2026, 9, 25), end_date=date(2026, 9, 25), decision_time="2026-09-26T01:00:00+00:00")

def test_runner_requires_lock_and_reports_success():
    lock, notifier, job = FakeLock(), FakeNotifier(), FakeJob(Result())
    runner = OperationalDailyRunner(job, lock=lock, notifier=notifier, token_factory=lambda: "token-1")
    result, report = run(runner)
    assert result is job.result
    assert report.run_id == "run-1" and report.symbols_ok == 10 and report.ranked == 2 and report.notified
    assert lock.tokens == ["token-1"] and job.calls == 1

def test_runner_does_not_hide_job_failure():
    lock, notifier, job = FakeLock(), FakeNotifier(), FakeJob(error=ValueError("boom"))
    runner = OperationalDailyRunner(job, lock=lock, notifier=notifier, token_factory=lambda: "token-2")
    with pytest.raises(RuntimeError, match="daily recommendation run failed"): run(runner)
    assert job.calls == 1 and notifier.messages == ["paper-live daily run FAILED: ValueError"]

def test_runner_does_not_fail_open_on_empty_lock_token():
    runner = OperationalDailyRunner(FakeJob(Result()), lock=FakeLock(), token_factory=lambda: "")
    with pytest.raises(RuntimeError, match="lock token"): run(runner)
