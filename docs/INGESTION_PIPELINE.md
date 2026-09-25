# Ingestion pipeline

`IngestionPipeline` is the data-only orchestration boundary for daily market datasets.

```text
SecurityMaster snapshot
        |
        v
 deterministic market batches
        |
        v
 provider factory -> resilient collector
        |
        v
 normalized + point-in-time validated rows
        |
        v
 Google Drive dataset + checksum manifest
        |
        v
 ingestion run ledger + failure artifact
```

## Guarantees

- Active securities are sorted deterministically before batching.
- A provider is selected by market; provider credentials remain outside the job and manifests.
- Collection retries/rate limits are delegated to `ResilientDailyCollector`.
- Dataset rows are normalized and require `available_at` so future information cannot silently enter historical features.
- Run IDs are deterministic for the same market/date/universe request.
- Run metadata contains counts and dataset references, never API keys or tokens.
- The pipeline does not create, preview, submit, or cancel trade orders.

## Resume model

A run manifest and `failures.jsonl` are written through `IngestionRunLedger`. The failure queue is deterministic and de-duplicated. A future scheduler can consume only retryable failures without rerunning the entire universe.

Production should treat the dataset manifest as the publication record and the run manifest as the operational record. If dataset publication fails, the run must not be represented as a successfully published dataset.
