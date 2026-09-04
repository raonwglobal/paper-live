from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from math import sqrt


@dataclass(frozen=True)
class OHLCV:
    timestamp: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


def sma(values: Sequence[Decimal], period: int) -> list[Decimal | None]:
    if period <= 0:
        raise ValueError("period must be positive")
    out: list[Decimal | None] = [None] * len(values)
    for i in range(period - 1, len(values)):
        out[i] = sum(values[i - period + 1 : i + 1], Decimal("0")) / Decimal(period)
    return out


def ema(values: Sequence[Decimal], period: int) -> list[Decimal | None]:
    if period <= 0:
        raise ValueError("period must be positive")
    out: list[Decimal | None] = [None] * len(values)
    if len(values) < period:
        return out
    seed = sum(values[:period], Decimal("0")) / Decimal(period)
    out[period - 1] = seed
    alpha = Decimal("2") / Decimal(period + 1)
    for i in range(period, len(values)):
        out[i] = (values[i] - out[i - 1]) * alpha + out[i - 1]  # type: ignore[operator]
    return out


def rsi(values: Sequence[Decimal], period: int = 14) -> list[Decimal | None]:
    if period <= 0:
        raise ValueError("period must be positive")
    out: list[Decimal | None] = [None] * len(values)
    if len(values) <= period:
        return out
    gains = [max(values[i] - values[i - 1], Decimal("0")) for i in range(1, len(values))]
    losses = [max(values[i - 1] - values[i], Decimal("0")) for i in range(1, len(values))]
    avg_gain = sum(gains[:period], Decimal("0")) / Decimal(period)
    avg_loss = sum(losses[:period], Decimal("0")) / Decimal(period)
    out[period] = (
        Decimal("100") if avg_loss == 0 else Decimal("100") - Decimal("100") / (Decimal("1") + avg_gain / avg_loss)
    )
    for i in range(period + 1, len(values)):
        avg_gain = (avg_gain * Decimal(period - 1) + gains[i - 1]) / Decimal(period)
        avg_loss = (avg_loss * Decimal(period - 1) + losses[i - 1]) / Decimal(period)
        out[i] = (
            Decimal("100") if avg_loss == 0 else Decimal("100") - Decimal("100") / (Decimal("1") + avg_gain / avg_loss)
        )
    return out


@dataclass(frozen=True)
class ScreenRule:
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    min_volume: Decimal | None = None
    min_rsi: Decimal | None = None
    max_rsi: Decimal | None = None


def screen(candles: Sequence[OHLCV], rule: ScreenRule) -> list[OHLCV]:
    closes = [c.close for c in candles]
    rsis = rsi(closes)
    result: list[OHLCV] = []
    for i, candle in enumerate(candles):
        if rule.min_price is not None and candle.close < rule.min_price:
            continue
        if rule.max_price is not None and candle.close > rule.max_price:
            continue
        if rule.min_volume is not None and candle.volume < rule.min_volume:
            continue
        value = rsis[i]
        if rule.min_rsi is not None and (value is None or value < rule.min_rsi):
            continue
        if rule.max_rsi is not None and (value is None or value > rule.max_rsi):
            continue
        result.append(candle)
    return result


def sharpe_ratio(returns: Iterable[Decimal], risk_free: Decimal = Decimal("0")) -> Decimal:
    xs = [x - risk_free for x in returns]
    if len(xs) < 2:
        return Decimal("0")
    mean = sum(xs, Decimal("0")) / Decimal(len(xs))
    variance = sum((x - mean) ** 2 for x in xs) / Decimal(len(xs) - 1)
    if variance == 0:
        return Decimal("0")
    return mean / Decimal(str(sqrt(float(variance))))


def max_drawdown(equity: Sequence[Decimal]) -> Decimal:
    peak = None
    worst = Decimal("0")
    for value in equity:
        peak = value if peak is None or value > peak else peak
        if peak and peak != 0:
            drawdown = (value - peak) / peak
            if drawdown < worst:
                worst = drawdown
    return worst
