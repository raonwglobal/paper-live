# Daily Market Dataset

paper-live treats Google Drive as the durable dataset archive, not a transactional database.

## Canonical row
(market, symbol, trade_date) is the idempotency key. Rows contain OHLCV, optional value/adjusted close, source, currency, schema version, and available_at.

## Collection
Use one scheduled collector after each market close. It applies bounded retries and rate limiting and reports per-symbol failures so only failed symbols need another run. Providers implement DailyPriceProvider; authentication remains behind SecretBroker.

## ML/recommendation
Feature jobs consume only rows whose available_at is at or before the decision timestamp. Derived datasets should include returns, volatility, moving averages, momentum, volume ratios, and market-relative returns, retaining the source dataset checksum.
