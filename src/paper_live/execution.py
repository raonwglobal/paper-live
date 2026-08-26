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
    status: str = "FILLED"


@dataclass
class PaperAccount:
    cash: Decimal
    positions: Dict[str, Decimal] = field(default_factory=dict)


class VirtualMatchingEngine:
    """Deterministic local paper matching engine with configurable slippage."""

    def __init__(self, account: PaperAccount, fee_rate: Decimal = Decimal("0.00015"), sell_tax_rate: Decimal = Decimal("0.002"), slippage_bps: Decimal = Decimal("5"), max_fill_ratio: Decimal = Decimal("1")):
        self.account = account
        self.fee_rate = fee_rate
        self.sell_tax_rate = sell_tax_rate
        self.slippage_bps = slippage_bps
        self.max_fill_ratio = max_fill_ratio

    def execute(self, order: OrderRequest, market_price: Decimal, available_quantity: Decimal | None = None) -> Fill:
        if order.quantity <= 0 or market_price <= 0:
            raise ValueError("quantity and market_price must be positive")
        if self.slippage_bps < 0 or self.max_fill_ratio <= 0 or self.max_fill_ratio > 1:
            raise ValueError("invalid matching parameters")
        if order.order_type == OrderType.LIMIT:
            if order.limit_price is None:
                raise ValueError("limit_price required")
            if order.side == OrderSide.BUY and market_price > order.limit_price:
                raise ValueError("limit buy not marketable")
            if order.side == OrderSide.SELL and market_price < order.limit_price:
                raise ValueError("limit sell not marketable")

        fill_qty = order.quantity * self.max_fill_ratio
        if available_quantity is not None:
            fill_qty = min(fill_qty, available_quantity)
        if fill_qty <= 0:
            return Fill(order.client_order_id, order.symbol, order.side, Decimal("0"), market_price, Decimal("0"), Decimal("0"), "REJECTED")
        slip = self.slippage_bps / Decimal("10000")
        fill_price = market_price * (Decimal("1") + slip if order.side == OrderSide.BUY else Decimal("1") - slip)
        gross = (fill_qty * fill_price).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        fee = (gross * self.fee_rate).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        tax = (gross * self.sell_tax_rate).quantize(Decimal("0.01"), rounding=ROUND_DOWN) if order.side == OrderSide.SELL else Decimal("0.00")
        position = self.account.positions.get(order.symbol, Decimal("0"))

        if order.side == OrderSide.BUY:
            total = gross + fee
            if self.account.cash < total:
                raise ValueError("insufficient paper cash")
            self.account.cash -= total
            self.account.positions[order.symbol] = position + fill_qty
        else:
            if position < fill_qty:
                raise ValueError("insufficient paper position")
            self.account.positions[order.symbol] = position - fill_qty
            self.account.cash += gross - fee - tax

        status = "FILLED" if fill_qty == order.quantity else "PARTIALLY_FILLED"
        return Fill(order.client_order_id, order.symbol, order.side, fill_qty, fill_price, fee, tax, status)


class ExecutionGateway:
    """Mandatory policy gate before any execution implementation is called."""

    def __init__(self, controller: EnvironmentController, paper: VirtualMatchingEngine):
        self.controller = controller
        self.paper = paper

    def execute(self, order: OrderRequest, market_price: Decimal, available_quantity: Decimal | None = None) -> Fill:
        mode = self.controller.get_current_mode()
        if mode in {ExecutionEnvironmentMode.PAPER_SANDBOX, ExecutionEnvironmentMode.VIRTUAL_BACKTEST}:
            self.controller.assert_skill_allowed("skill-virtual-matching-engine")
            return self.paper.execute(order, market_price, available_quantity)
        raise EnvironmentTransitionError("REAL_LIVE execution requires an explicitly authorized broker adapter; paper gateway refuses it")
