from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Iterable
from .executor import PluginSkillExecutor
from .lifecycle import PluginLifecycle, PluginState
from .policy import PluginExecutionPolicy

@dataclass(frozen=True)
class BacktestBar:
    timestamp: str
    symbol: str
    price: Decimal

@dataclass(frozen=True)
class BacktestResult:
    bars: int
    signals: int
    orders: int
    final_cash: Decimal

class PluginBacktestRunner:
    """Deterministic orchestration boundary; broker execution remains outside plugins."""
    def __init__(self, lifecycle: PluginLifecycle, executor: PluginSkillExecutor,
                 policy: PluginExecutionPolicy | None = None):
        self.lifecycle = lifecycle
        self.executor = executor
        self.policy = policy or PluginExecutionPolicy()

    def run(self, plugin_id: str, skill_id: str, bars: Iterable[BacktestBar],
            initial_cash: Decimal, signal_to_order: Callable[[dict, BacktestBar], Decimal | None]) -> BacktestResult:
        record = self.lifecycle.get(plugin_id)
        if record.state != PluginState.ENABLED:
            raise PermissionError("plugin must be enabled")
        self.policy.check("VIRTUAL_BACKTEST")
        cash = initial_cash
        signals = orders = count = 0
        for bar in bars:
            count += 1
            signal = self.executor.execute(skill_id, mode="VIRTUAL_BACKTEST", symbol=bar.symbol, price=bar.price)
            signals += 1 if signal else 0
            quantity = signal_to_order(signal, bar)
            if quantity is not None and quantity > 0:
                cash -= quantity * bar.price
                orders += 1
        return BacktestResult(count, signals, orders, cash)
