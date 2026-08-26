import pytest
from paper_live.environment import EnvironmentTransitionError, ExecutionEnvironmentMode
from paper_live.live_approval import LiveApprovalGate

def test_live_requires_explicit_approval():
    gate = LiveApprovalGate()
    with pytest.raises(EnvironmentTransitionError):
        gate.require(ExecutionEnvironmentMode.REAL_LIVE)
    gate.approve("operator", "approved production promotion")
    gate.require(ExecutionEnvironmentMode.REAL_LIVE)

def test_revoke_removes_live_approval():
    gate = LiveApprovalGate()
    gate.approve("operator", "test")
    gate.revoke()
    with pytest.raises(EnvironmentTransitionError):
        gate.require(ExecutionEnvironmentMode.REAL_LIVE)
