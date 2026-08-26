from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Sequence
from uuid import uuid4

from .analytics import OHLCV, max_drawdown, sharpe_ratio
from .execution import ExecutionGateway, OrderRequest, PaperAccount


@dataclass(frozen=True)
class BacktestResult:
    initial_cash: Decimal
    final_cash: Decimal
    equity_curve: tuple[Decimal, ...]
    fills: int
    sharpe: Decimal
    max_drawdown: Decimal


class BacktestRunner:
    def __init__(self, gateway: ExecutionGateway, account: PaperAccount):
        self.gateway = gateway
        self.account = account

    def run(self, candles: Sequence[OHLCV], strategy: Callable[[int, Sequence[OHLCV]], OrderRequest | None]) -> BacktestResult:
        initial = self.account.cash
        equity: list[Decimal] = []
        fills = 0
        for i, candle in enumerate(candles):
            order = strategy(i, candles[:i + 1])
            if order is not None:
                if not order.client_order_id:
                    order = OrderRequest(order.symbol, order.side, order.quantity, order.order_type, order.limit_price, f"backtest-{i}-{uuid4().hex[:12]}")
                self.gateway.execute(order, candle.close)
                fills += 1
            position_value = sum((qty * candle.close for symbol, qty in self.account.positions.items()), Decimal("0"))
            equity.append(self.account.cash + position_value)
        returns = []
        for i in range(1, len(equity)):
            if equity[i - 1] != 0:
                returns.append(equity[i] / equity[i - 1] - Decimal("1"))
        final = equity[-1] if equity else initial
        return BacktestResult(initial, final, tuple(equity), fills, sharpe_ratio(returns), max_drawdown(equity))
