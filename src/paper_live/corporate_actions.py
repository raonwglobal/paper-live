from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable, Sequence

@dataclass(frozen=True)
class CorporateAction:
    market: str
    symbol: str
    action_date: date
    action_type: str
    ratio: Decimal | None = None
    cash_amount: Decimal | None = None
    currency: str | None = None
    source: str = ""
    effective_from: date | None = None

class CorporateActionBook:
    """Immutable-style corporate-action registry. Actions are separate from price history."""

    VALID_TYPES=frozenset({"SPLIT","REVERSE_SPLIT","CASH_DIVIDEND","STOCK_DIVIDEND","DELISTING","LISTING","RIGHTS"})
    def __init__(self, actions: Sequence[CorporateAction] = ()):
        self._actions: tuple[CorporateAction,...]=()
        self.replace(actions)

    def replace(self, actions: Iterable[CorporateAction]) -> None:
        normalized=[]
        seen=set()
        for a in actions:
            typ=a.action_type.upper()
            if typ not in self.VALID_TYPES: raise ValueError(f"unsupported action_type: {typ}")
            if not a.symbol or not a.market: raise ValueError("market and symbol are required")
            if a.ratio is not None and a.ratio <= 0: raise ValueError("ratio must be positive")
            key=(a.market.upper(),a.symbol.upper(),a.action_date,typ,a.ratio,a.cash_amount)
            if key in seen: continue
            seen.add(key)
            normalized.append(CorporateAction(a.market.upper(),a.symbol.upper(),a.action_date,typ,a.ratio,a.cash_amount,a.currency,a.source,a.effective_from))
        self._actions=tuple(sorted(normalized,key=lambda x:(x.market,x.symbol,x.action_date,x.action_type)))

    def for_symbol(self, market: str, symbol: str, start: date | None=None, end: date | None=None) -> tuple[CorporateAction,...]:
        return tuple(a for a in self._actions if a.market==market.upper() and a.symbol==symbol.upper() and (start is None or a.action_date>=start) and (end is None or a.action_date<=end))

    def adjustment_factor(self, market: str, symbol: str, as_of: date) -> Decimal:
        factor=Decimal("1")
        for a in self.for_symbol(market,symbol,end=as_of):
            if a.action_type=="SPLIT" and a.ratio: factor*=a.ratio
            elif a.action_type=="REVERSE_SPLIT" and a.ratio: factor/=a.ratio
        return factor
