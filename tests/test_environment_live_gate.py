import hashlib
import hmac
import pytest
from paper_live.environment import EnvironmentController, EnvironmentTransitionError, ExecutionEnvironmentMode
from paper_live.live_approval import LiveApprovalGate

def token(secret: str) -> str:
    return hmac.new(secret.encode(), b"environment-transition", hashlib.sha256).hexdigest()

def test_controller_rejects_live_without_gate():
    secret = "test-secret"
    controller = EnvironmentController(transition_secret=secret)
    with pytest.raises(EnvironmentTransitionError):
        controller.set_mode(ExecutionEnvironmentMode.REAL_LIVE, token(secret))

def test_controller_requires_and_accepts_explicit_live_approval():
    secret = "test-secret"
    gate = LiveApprovalGate()
    controller = EnvironmentController(transition_secret=secret, live_approval_gate=gate)
    with pytest.raises(EnvironmentTransitionError):
        controller.set_mode(ExecutionEnvironmentMode.REAL_LIVE, token(secret))
    gate.approve("operator", "controlled promotion test")
    assert controller.set_mode(ExecutionEnvironmentMode.REAL_LIVE, token(secret)) is True
    assert controller.get_current_mode() is ExecutionEnvironmentMode.REAL_LIVE
