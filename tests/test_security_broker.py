from decimal import Decimal

import pytest

from paper_live.brokers import TossBrokerAdapter
from paper_live.security import CredentialProvider, LiveApprovalGate


def test_live_approval_requires_valid_nonce():
    gate = LiveApprovalGate()
    with pytest.raises(PermissionError):
        gate.approve("operator", "bad")
    gate.approve("operator", gate.nonce)
    assert gate.approved()


def test_toss_requires_credentials(monkeypatch):
    monkeypatch.delenv("TOSS_API_TOKEN", raising=False)
    monkeypatch.delenv("TOSS_ACCOUNT_SEQ", raising=False)
    with pytest.raises(Exception):
        CredentialProvider().load_toss()


def test_toss_submit_is_disabled_by_default(monkeypatch):
    monkeypatch.setenv("TOSS_API_TOKEN", "dummy")
    monkeypatch.setenv("TOSS_ACCOUNT_SEQ", "1")
    monkeypatch.delenv("PAPER_LIVE_ENABLE_LIVE", raising=False)
    adapter = TossBrokerAdapter()
    with pytest.raises(PermissionError):
        adapter.submit("005930", "BUY", Decimal("1"), Decimal("70000"))
