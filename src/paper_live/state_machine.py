from __future__ import annotations

from enum import Enum
from dataclasses import dataclass


class CycleState(str, Enum):
    INGESTED = "INGESTED"
    ANALYZED = "ANALYZED"
    DEBATED = "DEBATED"
    RISK_APPROVED = "RISK_APPROVED"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"
    REFLECTED = "REFLECTED"


@dataclass
class CycleStateMachine:
    state: CycleState = CycleState.INGESTED

    def advance(self, target: CycleState) -> None:
        allowed = {
            CycleState.INGESTED: {CycleState.ANALYZED, CycleState.REJECTED},
            CycleState.ANALYZED: {CycleState.DEBATED, CycleState.REJECTED},
            CycleState.DEBATED: {CycleState.RISK_APPROVED, CycleState.REJECTED},
            CycleState.RISK_APPROVED: {CycleState.EXECUTED, CycleState.REJECTED},
            CycleState.EXECUTED: {CycleState.REFLECTED},
            CycleState.REJECTED: {CycleState.REFLECTED},
            CycleState.REFLECTED: set(),
        }
        if target not in allowed[self.state]:
            raise ValueError(f"invalid state transition: {self.state} -> {target}")
        self.state = target
