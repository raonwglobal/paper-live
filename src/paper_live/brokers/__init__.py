"""Broker adapter package.

The package form is intentional: the broker protocol, safety router, and
individual broker adapters must not be shadowed by a legacy ``brokers.py``
module.
"""

from .protocol import BrokerAdapter, OrderRequest, OrderResult, LiveBrokerDenied
from .safe_router import BrokerRouter
from .toss import TossBrokerAdapter, TossCredentials, TossApiError
from .kb import KbBrokerAdapter, KbCredentials, KbApiError

# Backward-compatible spelling used by older callers.
KBBrokerAdapter = KbBrokerAdapter

__all__ = [
    "BrokerAdapter",
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
