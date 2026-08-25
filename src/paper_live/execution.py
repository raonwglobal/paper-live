from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN
from enum import Enum
from typing import Dict

from .environment import EnvironmentController, EnvironmentTransitionError, ExecutionEnvironmentMode


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    side: OrderSide
    quantity: Decimal
    order_type: OrderType = OrderType.MARKET
    limit_price: Decimal | None = None
    client_order_id: str = ""


@dataclass(frozen=True)
class Fill:
    order_id: str
    symbol: str
    side: OrderSide
    quantity: Decimal
    price: Decimal
    fee: Decimal
    tax: Decimal


@dataclass
class PaperAccount:
    cash: Decimal
    positions: Dict[str, Decimal] = field(default_factory=dict)


class VirtualMatchingEngine:
    """Deterministic local paper matching engine; no network access."""

    def __init__(self, account: PaperAccount, fee_rate: Decimal = Decimal("0.00015"), sell_tax_rate: Decimal = Decimal("0.002")):
        self.account = account
        self.fee_rate = fee_rate
        self.sell_tax_rate = sell_tax_rate

    def execute(self, order: OrderRequest, market_price: Decimal) -> Fill:
        if order.quantity <= 0 or market_price <= 0:
            raise ValueError("quantity and market_price must be positive")
        if order.order_type == OrderType.LIMIT:
            if order.limit_price is None:
                raise ValueError("limit_price required")
            if order.side == OrderSide.BUY and market_price > order.limit_price:
                raise ValueError("limit buy not marketable")
            if order.side == OrderSide.SELL and market_price < order.limit_price:
                raise ValueError("limit sell not marketable")

        gross = (order.quantity * market_price).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        fee = (gross * self.fee_rate).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        tax = (gross * self.sell_tax_rate).quantize(Decimal("0.01"), rounding=ROUND_DOWN) if order.side == OrderSide.SELL else Decimal("0.00")
        position = self.account.positions.get(order.symbol, Decimal("0"))

        if order.side == OrderSide.BUY:
            total = gross + fee
            if self.account.cash < total:
                raise ValueError("insufficient paper cash")
            self.account.cash -= total
            self.account.positions[order.symbol] = position + order.quantity
        else:
            if position < order.quantity:
                raise ValueError("insufficient paper position")
            self.account.positions[order.symbol] = position - order.quantity
            self.account.cash += gross - fee - tax

        return Fill(order.client_order_id, order.symbol, order.side, order.quantity, market_price, fee, tax)


class ExecutionGateway:
    """Mandatory policy gate before any execution implementation is called."""

    def __init__(self, controller: EnvironmentController, paper: VirtualMatchingEngine):
        self.controller = controller
        self.paper = paper

    def execute(self, order: OrderRequest, market_price: Decimal) -> Fill:
        mode = self.controller.get_current_mode()
        if mode in {ExecutionEnvironmentMode.PAPER_SANDBOX, ExecutionEnvironmentMode.VIRTUAL_BACKTEST}:
            self.controller.assert_skill_allowed("skill-virtual-matching-engine")
            return self.paper.execute(order, market_price)
        raise EnvironmentTransitionError(
            "REAL_LIVE execution requires an explicitly authorized broker adapter; paper gateway refuses it"
        )
