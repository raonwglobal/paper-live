# Operations

## Daily runner

`OperationalDailyRunner` is the production boundary around `DailyRecommendationJob`.

It requires a distributed `ExecutionLock` and never falls back to an in-process lock. This prevents concurrent schedulers from publishing duplicate daily runs.

Example:

    runner = OperationalDailyRunner(
        daily_job,
        lock=RedisLeaseLock(...),
        notifier=TelegramNotifier(),
    )
    result, report = runner.run(
        start_date=trade_date,
        end_date=trade_date,
        decision_time=decision_time,
    )

Safety behavior:

- Empty lock tokens are rejected.
- Lock acquisition failures prevent the job from running.
- Job failures are re-raised after a best-effort alert.
- Notification failures never authorize or block trading.
- Alert messages contain run statistics only; credentials are never included.

The scheduler and provider/universe credentials remain outside source control.
