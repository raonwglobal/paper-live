# Operations

## Daily runner

`OperationalDailyRunner` is the production boundary around `DailyRecommendationJob`.

It requires a distributed `ExecutionLock` and never falls back to an in-process lock. This prevents concurrent schedulers from publishing duplicate daily runs.

### CLI entry point

Install the optional Redis dependency and configure a factory that constructs the project-specific job:

```bash
pip install -e '.[operations]'
export REDIS_URL='rediss://...'
export PAPER_LIVE_JOB_FACTORY='deployment.paper_live_factory:build_daily_job'
export TELEGRAM_BOT_TOKEN='...'
export TELEGRAM_CHAT_ID='...'

paper-live-daily \
  --start-date 2026-09-28 \
  --end-date 2026-09-28 \
  --decision-time 2026-09-29T00:30:00+00:00
```

The factory must be importable in the deployment environment and return a configured `DailyRecommendationJob`. This keeps provider credentials, market universe, Google Drive configuration, and deployment-specific choices out of the library and source control. A scheduler (systemd timer, Kubernetes CronJob, or managed scheduler) can invoke this command after the relevant market close. Do not configure live execution through this entry point.

### Configuration and safety

- `PAPER_LIVE_JOB_FACTORY` must be a `module:callable` reference.
- `REDIS_URL` is mandatory; lock acquisition errors abort the run.
- Date range and decision timestamp are explicit command-line arguments.
- Telegram notification is best-effort; missing notification credentials do not authorize or block execution.
- Job failures return a non-zero process exit through the raised runner exception.
- Alert messages contain run statistics only; credentials are never included.
- Keep secrets in the deployment secret manager, not in workflow files or checked-in environment files.
