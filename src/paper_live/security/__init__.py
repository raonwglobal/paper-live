"""Security primitives for live execution boundaries.

Canonical modules live in this package. The legacy top-level
``paper_live.security`` module was removed because it was shadowed by
this package directory.

Live approval is intentionally split:
- ``paper_live.live_approval.LiveApprovalGate`` — environment promotion
- ``paper_live.security.live_approval_gate.LiveApprovalGate`` — order auth
"""

from .live_approval_gate import LiveApprovalGate
from .secrets import CredentialError, CredentialProvider, BrokerCredentials

__all__ = ["LiveApprovalGate", "CredentialError", "CredentialProvider", "BrokerCredentials"]
