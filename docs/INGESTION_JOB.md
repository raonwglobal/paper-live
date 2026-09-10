# Market ingestion job

The job is the orchestration boundary for daily collection. It obtains active securities from SecurityMaster, groups them into deterministic batches, selects a provider per market, and delegates retries/rate limiting to ResilientDailyCollector. A run reports aggregate successes and failures without hiding partial completion.

Production scheduling should invoke this job after the relevant market close and persist the returned run metadata alongside the dataset manifest. Credentials are injected into provider factories and are never written to manifests or logs.
