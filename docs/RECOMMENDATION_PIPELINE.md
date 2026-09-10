# Reproducible feature/recommendation pipeline

The canonical daily market dataset is transformed into point-in-time features and a recommendation snapshot.

## Flow

`daily_prices -> DailyFeatureEngine -> features/daily -> StockRecommendationAgent -> recommendations/daily`

Each feature/recommendation row carries the SHA-256 checksum of the ordered daily input snapshot. The recommendation output also records `decision_time` and `dataset_version`.

## Point-in-time rule

A daily row is eligible only when `available_at <= decision_time`. This prevents future information from entering a historical decision.

## Publication

Feature and recommendation snapshots are written through the existing data-lake abstraction. The resulting manifests provide row counts, schema versions, as-of timestamps, and checksums for reproducibility.

No broker credential or order API is used by this pipeline.
