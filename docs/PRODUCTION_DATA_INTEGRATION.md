# Production data integration

This project now provides reusable configuration helpers; deployment-specific provider credentials and market membership remain outside the package.

## Security universe

Mount a CSV file into the deployment with columns:

```csv
symbol,name,market,currency,active
005930,Samsung Electronics,KOSPI,KRW,true
AAPL,Apple Inc.,NASDAQ,USD,true
```

- `symbol`, `name`, and `market` are required.
- `currency` defaults to KRW; `active` defaults to true.
- Duplicate (market, symbol) pairs are rejected by `SecurityMaster`.
- Keep the CSV in a reviewed configuration repository or mounted secret/config volume; refresh it on a controlled schedule and retain dated snapshots for reproducibility.

Load it with `load_security_master_csv(path)` from `paper_live.deployment_config`.

## Google Drive archive

Set `GOOGLE_DRIVE_DATA_ACCESS_TOKEN` (preferred) or `GOOGLE_DRIVE_ACCESS_TOKEN`. Optionally set `GOOGLE_DRIVE_DATA_FOLDER_ID` to choose the archive root and `GOOGLE_DRIVE_DATA_SHARED_DRIVE_ID` for a shared drive. Use a least-privilege service identity and keep token rotation in the deployment secret manager.

`build_google_drive_storage()` constructs the existing `GoogleDriveStorageAgent`. The archive stores versioned JSONL datasets and manifests; it is not a transactional database. Validate Drive permissions with a small, non-production dataset before enabling scheduled ingestion.

## Provider adapter contract

The daily job expects a `provider_factory(market)` returning an implementation of `DailyPriceProvider`. Provider adapters must normalize results into the project's `DailyPriceRecord` schema, preserve exchange trading dates, report unsupported symbols explicitly, and implement provider-specific rate limits/retries. Do not silently substitute missing prices or mix adjusted and unadjusted prices.

## Deployment factory

Set `PAPER_LIVE_JOB_FACTORY=your_deployment_module:build_daily_job`. That factory should load the reviewed universe CSV, call `build_google_drive_storage()`, construct the chosen provider factory, and return `DailyRecommendationJob`. Provider selection and credentials cannot be safely hard-coded in this repository.

## Rollout checklist

1. Validate universe counts and sample symbols per market.
2. Confirm provider licensing, historical coverage, timezone, adjustment policy, and rate limits.
3. Upload and read back a small sample dataset in a staging Drive folder.
4. Compare collected OHLCV against an independent source for selected symbols.
5. Run the daily job in paper-only mode and inspect manifests/failure queues for several sessions.
6. Only then configure the production scheduler. Live order submission remains disabled by this integration.
