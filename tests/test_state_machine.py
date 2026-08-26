import pytest
from paper_live.state_machine import CycleState, CycleStateMachine


def test_cycle_state_machine_happy_path():
    m = CycleStateMachine()
    for state in [CycleState.ANALYZED, CycleState.DEBATED, CycleState.RISK_APPROVED, CycleState.EXECUTED, CycleState.REFLECTED]:
        m.advance(state)
    assert m.state is CycleState.REFLECTED


def test_cycle_state_machine_rejects_skip():
    m = CycleStateMachine()
    with pytest.raises(ValueError):
        m.advance(CycleState.EXECUTED)
