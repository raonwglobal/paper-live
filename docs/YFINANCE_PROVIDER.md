# Yahoo Finance provider adapter

Install with `pip install -e '.[yfinance]'` to enable the optional `YFinanceDailyPriceProvider`. The core package does not import yfinance unless the provider is instantiated and used.

The adapter implements `DailyPriceProvider.fetch_daily_prices` and returns raw OHLCV plus adjusted close. It requests unadjusted OHLC values and handles Yahoo's exclusive end-date convention by advancing the requested end date by one day. KOSPI symbols are mapped to `.KS` and KOSDAQ symbols to `.KQ`; other market symbols are passed through unchanged.

Example deployment factory wiring:

```python
from paper_live.yfinance_provider import YFinanceDailyPriceProvider

def provider_factory(market: str):
    return YFinanceDailyPriceProvider(market=market)
```

**Limitations:** Yahoo Finance is a community-accessed data source, not a guaranteed exchange-grade feed. Coverage, corporate-action adjustments, rate limits, symbol mappings, and data availability can change. Confirm terms of use and validate representative records against an authoritative source before production use. For institutional or licensed feeds, implement another adapter against the same `DailyPriceProvider` protocol. Do not treat missing rows as zero prices.
