"""Broker adapter package.

The package form is intentional: the broker protocol, safety router, and
individual broker adapters must not be shadowed by a legacy ``brokers.py``
module.
"""

from .kb import KbApiError, KbBrokerAdapter, KbCredentials
from .protocol import BrokerAdapter, BrokerOrderRequest, LiveBrokerDenied, OrderResult
from .safe_router import BrokerRouter
from .toss import TossApiError, TossBrokerAdapter, TossCredentials

# Backward-compatible spelling used by older callers.
KBBrokerAdapter = KbBrokerAdapter
# Backward-compatible alias for the order DTO.
OrderRequest = BrokerOrderRequest

__all__ = [
    "BrokerAdapter",
    "BrokerOrderRequest",
    "OrderRequest",
    "OrderResult",
    "LiveBrokerDenied",
    "BrokerRouter",
    "TossBrokerAdapter",
    "TossCredentials",
    "TossApiError",
    "KbBrokerAdapter",
    "KBBrokerAdapter",
    "KbCredentials",
    "KbApiError",
]
