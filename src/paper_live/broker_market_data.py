from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .market_dataset import DailyPriceProvider


class BrokerMarketDataError(RuntimeError):
    pass


def _json_request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: int = 20,
):
    req = Request(url, method=method, headers=headers or {}, data=body)
    try:
        with urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise BrokerMarketDataError(f"market data request failed: {type(exc).__name__}") from exc


@dataclass(frozen=True)
class TossCredentials:
    client_id: str
    client_secret: str
    account: str | None = None


class TossTokenProvider:
    def __init__(
        self, credentials: TossCredentials, base_url: str = "https://openapi.tossinvest.com", timeout: int = 20
    ):
        self.credentials, self.base_url, self.timeout = credentials, base_url.rstrip("/"), timeout
        self._token: str | None = None

    def token(self) -> str:
        form = urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": self.credentials.client_id,
                "client_secret": self.credentials.client_secret,
            }
        ).encode()
        payload = _json_request(
            self.base_url + "/oauth2/token",
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            body=form,
            timeout=self.timeout,
        )
        token = payload.get("access_token")
        if not token:
            raise BrokerMarketDataError("Toss token response did not contain access_token")
        self._token = token
        return token


class TossDailyPriceProvider(DailyPriceProvider):
    """Toss Open API daily candle adapter; read-only market data only."""

    def __init__(self, credentials: TossCredentials, *, adjusted: bool = True, timeout: int = 20):
        self.credentials, self.adjusted, self.timeout = credentials, adjusted, timeout
        self.tokens = TossTokenProvider(credentials, timeout=timeout)

    def _get(self, path: str, params: dict[str, str | int | bool]) -> dict:
        headers = {"Authorization": f"Bearer {self.tokens.token()}"}
        if self.credentials.account:
            headers["X-Tossinvest-Account"] = self.credentials.account
        query = urlencode(params)
        return _json_request(f"https://openapi.tossinvest.com{path}?{query}", headers=headers, timeout=self.timeout)

    def fetch_daily_prices(self, symbol: str, start_date: date, end_date: date):
        if start_date > end_date:
            raise ValueError("start_date must not be after end_date")
        rows = []
        before: str | None = None
        for _ in range(100):
            params: dict[str, str | int | bool] = {
                "symbol": symbol,
                "interval": "1d",
                "count": 200,
                "adjusted": self.adjusted,
            }
            if before:
                params["before"] = before
            payload = self._get("/api/v1/candles", params)
            result = payload.get("result") or {}
            candles = result.get("candles") or []
            if not candles:
                break
            reached_older = False
            for candle in candles:
                ts = str(candle.get("timestamp", ""))
                day = date.fromisoformat(ts[:10])
                if day < start_date:
                    reached_older = True
                    continue
                if day <= end_date:
                    rows.append(
                        {
                            "symbol": symbol,
                            "trade_date": day.isoformat(),
                            "open": candle.get("openPrice"),
                            "high": candle.get("highPrice"),
                            "low": candle.get("lowPrice"),
                            "close": candle.get("closePrice"),
                            "volume": candle.get("volume"),
                            "currency": candle.get("currency"),
                            "adjusted_close": candle.get("closePrice") if self.adjusted else None,
                        }
                    )
            next_before = result.get("nextBefore")
            if reached_older or not next_before or next_before == before:
                break
            before = str(next_before)
        return rows


class KBMarketDataAdapter:
    """Configurable KB read-only adapter. Endpoint paths/fields are supplied from the KB API JSON catalog.

    KB documents specify HTTPS JSON, Bearer authentication and environment-specific base URLs.
    This avoids guessing undocumented endpoint IDs.
    """

    def __init__(self, access_token: str, base_url: str = "https://developer.kbsec.com:32484", timeout: int = 20):
        if not access_token:
            raise ValueError("access_token is required")
        self.access_token, self.base_url, self.timeout = access_token, base_url.rstrip("/"), timeout

    def get(self, endpoint: str, params: dict[str, str] | None = None) -> dict:
        if not endpoint.startswith("/"):
            endpoint = "/" + endpoint
        query = urlencode(params or {})
        url = self.base_url + endpoint + (("?" + query) if query else "")
        return _json_request(
            url,
            headers={"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"},
            timeout=self.timeout,
        )
