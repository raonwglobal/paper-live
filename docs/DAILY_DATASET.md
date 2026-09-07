# Daily Market Dataset

paper-live stores daily market data as a versioned dataset in Google Drive. Google Drive is the archive/distribution layer; the application should not treat it as a transactional database.

## Dataset contract

Each row is keyed by (market, symbol, trade_date) and contains OHLCV plus optional traded value and adjusted close. Every row also contains available_at, the earliest timestamp at which the row is allowed to be used by a strategy. This prevents look-ahead bias.

Recommended partition:
market/daily_prices/date=YYYY-MM-DD/market-daily_prices.jsonl

A manifest.json is written beside every snapshot and includes row count, schema version, source and SHA-256 checksum.

## Collection policy

1. Maintain a security master/symbol universe separately from prices.
2. Collect the full universe after the local market close rather than one request per agent.
3. Batch symbols where the broker API supports batching and obey provider rate limits.
4. Persist raw provider responses separately when licensing permits; use normalized data as the canonical ML input.
5. Re-run only failed symbols/dates and use (market, symbol, trade_date) for idempotency.
6. Keep available_at at the actual provider availability time.
7. Store corporate actions, dividends and splits as separate datasets instead of silently rewriting historical OHLCV.

## Google Drive layout

paper-live-data/
- market/daily_prices/date=YYYY-MM-DD/
- market/security_master/date=YYYY-MM-DD/
- market/corporate_actions/date=YYYY-MM-DD/
- market/adjustments/date=YYYY-MM-DD/
- features/daily/date=YYYY-MM-DD/
- manifests/

Use a dedicated service account/shared-drive folder with least-privilege access. Credentials are handled by SecretBroker and are not stored in this dataset.
