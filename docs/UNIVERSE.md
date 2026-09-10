# Security Universe

The security master is the single source of truth for batch collection. Each security is keyed by (market, symbol) and carries active status and currency. Batches are deterministic, which makes retries and audit manifests reproducible. Providers may refresh this master from their official instrument-list endpoints; broker credentials are never stored in the universe dataset.
