from __future__ import annotations

import argparse
import importlib
import os
from collections.abc import Callable
from datetime import date
from typing import cast

from .daily_recommendation_job import DailyRecommendationJob
from .locking import RedisLeaseLock
from .notify import TelegramNotifier
from .operations import OperationalDailyRunner


def _load_factory(spec: str) -> Callable[[], DailyRecommendationJob]:
    module_name, separator, attribute = spec.partition(":")
    if not separator or not module_name or not attribute:
        raise ValueError("PAPER_LIVE_JOB_FACTORY must use 'module:callable' format")
    factory = getattr(importlib.import_module(module_name), attribute)
    if not callable(factory):
        raise TypeError("configured job factory is not callable")
    return cast(Callable[[], DailyRecommendationJob], factory)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the paper-live daily recommendation job")
    parser.add_argument("--start-date", required=True, type=date.fromisoformat)
    parser.add_argument("--end-date", required=True, type=date.fromisoformat)
    parser.add_argument("--decision-time", required=True, help="ISO-8601 timestamp with timezone")
    parser.add_argument("--available-at", help="Optional ISO-8601 data availability timestamp")
    args = parser.parse_args()

    factory_spec = os.getenv("PAPER_LIVE_JOB_FACTORY", "")
    if not factory_spec:
        parser.error("PAPER_LIVE_JOB_FACTORY is required")
    if args.end_date < args.start_date:
        parser.error("--end-date must be on or after --start-date")

    job = _load_factory(factory_spec)()
    runner = OperationalDailyRunner(
        job,
        lock=RedisLeaseLock(),
        notifier=TelegramNotifier(),
    )
    _, report = runner.run(
        start_date=args.start_date,
        end_date=args.end_date,
        decision_time=args.decision_time,
        available_at=args.available_at,
    )
    print(
        f"run_id={report.run_id} status={report.status} symbols_ok={report.symbols_ok} "
        f"failures={report.failures} ranked={report.ranked} notified={report.notified}"
    )
    return 0 if report.status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
