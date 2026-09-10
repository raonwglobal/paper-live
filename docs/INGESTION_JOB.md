# Market ingestion job

The ingestion job is the orchestration boundary for daily collection. It obtains active securities from SecurityMaster, groups them into deterministic batches, selects a provider per market, and delegates retries/rate limiting to the resilient collector. A run reports aggregate successes and failures without hiding partial completion.

## Run ledger and resume model

Every production collection should persist an `IngestionRunManifest` and a deterministic `FailureQueue`. The ledger is implemented in `paper_live.ingestion_run`.

```text
market close
    |
    v
MarketIngestionJob
    |
    +--> provider / rate-limit / retry
    |
    +--> DailyDatasetBuilder --> dataset manifest
    |
    +--> IngestionRunLedger
            +--> runs/<market>/<run_id>/manifest.json
            +--> runs/<market>/<run_id>/failures.jsonl
```

`run_id` is derived from market, date range, and the sorted symbol universe. The same input set therefore produces the same run identifier. Failed symbol/date ranges are deduplicated and sorted, so a retry worker can safely consume `FailureQueue.retryable()` without duplicating work.

A run can have one of three states:

- `completed`: every requested symbol succeeded.
- `completed_with_failures`: at least one symbol succeeded and one or more failures remain.
- `failed`: no requested symbol succeeded.

The run manifest stores counts and the dataset checksum, but never credentials or access tokens. Provider credentials are injected at runtime through `SecretBroker`.

## Operational policy

1. Start one run after the relevant market close.
2. Persist the dataset manifest and run manifest independently.
3. If the run is `completed_with_failures`, enqueue only `FailureQueue.retryable()`.
4. Keep non-retryable failures for operator review; do not spin indefinitely.
5. A successful retry must create a new dataset snapshot or a deterministic replacement according to the dataset retention policy; never silently mutate a historical snapshot.
6. Feature generation and recommendation must consume a validated dataset manifest and preserve its checksum in downstream audit metadata.
7. Credentials are injected into provider factories and are never written to manifests, failure records, or logs.

## Local/offline testing

`LocalDriveMirror` can be passed to `IngestionRunLedger` in tests. Production uses the same `DriveClient` boundary as `GoogleDriveStorageAgent`.
