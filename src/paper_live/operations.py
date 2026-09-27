from __future__ import annotations

from collections.abc import Callable, ContextManager
from dataclasses import dataclass
from datetime import date
from typing import Protocol
from uuid import uuid4

from .daily_recommendation_job import DailyRecommendationJob, DailyRecommendationJobResult

class ExecutionLock(Protocol):
    def acquire(self, token: str) -> ContextManager[None]: ...

class Notifier(Protocol):
    def send(self, message: str) -> bool: ...

@dataclass(frozen=True)
class OperationalRunReport:
    run_id: str
    status: str
    symbols_ok: int
    failures: int
    ranked: int
    notified: bool

class OperationalDailyRunner:
    """Production boundary around the deterministic daily recommendation job."""
    def __init__(self, job: DailyRecommendationJob, *, lock: ExecutionLock, notifier: Notifier | None = None, token_factory: Callable[[], str] | None = None) -> None:
        self.job = job
        self.lock = lock
        self.notifier = notifier
        self.token_factory = token_factory or (lambda: uuid4().hex)

    def run(self, *, start_date: date, end_date: date, decision_time: str, available_at: str | None = None) -> tuple[DailyRecommendationJobResult, OperationalRunReport]:
        token = self.token_factory()
        if not token: raise RuntimeError("execution lock token must not be empty")
        with self.lock.acquire(token):
            try:
                result = self.job.run(start_date=start_date, end_date=end_date, decision_time=decision_time, available_at=available_at)
            except Exception as exc:
                notified = self._notify(f"paper-live daily run FAILED: {type(exc).__name__}")
                raise RuntimeError(f"daily recommendation run failed; notification_sent={notified}") from exc
            ingestion = result.ingestion.manifest
            report = OperationalRunReport(ingestion.run_id, ingestion.status, ingestion.succeeded_symbols, ingestion.failed_symbols, len(result.ranked), self._notify(
                "paper-live daily run COMPLETED: "
                f"run_id={ingestion.run_id} symbols_ok={ingestion.succeeded_symbols} failures={ingestion.failed_symbols} ranked={len(result.ranked)}"
            ))
            return result, report

    def _notify(self, message: str) -> bool:
        if self.notifier is None: return False
        try: return bool(self.notifier.send(message))
        except Exception: return False
