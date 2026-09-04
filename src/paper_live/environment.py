from __future__ import annotations

import hashlib
import hmac
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .live_approval import LiveApprovalGate


class ExecutionEnvironmentMode(str, Enum):
    PAPER_SANDBOX = "PAPER_SANDBOX"
    VIRTUAL_BACKTEST = "VIRTUAL_BACKTEST"
    REAL_LIVE = "REAL_LIVE"


class EnvironmentTransitionError(RuntimeError):
    pass


@dataclass(frozen=True)
class EnvironmentSnapshot:
    mode: ExecutionEnvironmentMode
    version: int
    changed_at: datetime
    changed_by: str


@dataclass
class EnvironmentController:
    initial_mode: ExecutionEnvironmentMode = ExecutionEnvironmentMode.PAPER_SANDBOX
    transition_secret: str | None = None
    live_approval_gate: LiveApprovalGate | None = None
    _mode: ExecutionEnvironmentMode = field(init=False)
    _version: int = field(default=0, init=False)
    _changed_at: datetime = field(default_factory=lambda: datetime.now(UTC), init=False)
    _changed_by: str = field(default="system", init=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)
    _time_triggers: dict[str, ExecutionEnvironmentMode] = field(default_factory=dict, init=False)
    _kpi_triggers: dict[str, tuple[float, ExecutionEnvironmentMode]] = field(default_factory=dict, init=False)
    ALLOWED_SKILLS: dict[ExecutionEnvironmentMode, frozenset[str]] = field(
        default_factory=lambda: {
            ExecutionEnvironmentMode.PAPER_SANDBOX: frozenset({"skill-virtual-matching-engine", "skill-market-data"}),
            ExecutionEnvironmentMode.VIRTUAL_BACKTEST: frozenset(
                {"skill-virtual-matching-engine", "skill-historical-data"}
            ),
            ExecutionEnvironmentMode.REAL_LIVE: frozenset(
                {"skill-toss-broker", "skill-kb-broker", "skill-market-data", "skill-risk-circuit-breaker"}
            ),
        },
        init=False,
    )

    def __post_init__(self) -> None:
        self._mode = self.initial_mode
        if self._mode is ExecutionEnvironmentMode.REAL_LIVE:
            if self.live_approval_gate is None or not self.live_approval_gate.approved():
                raise EnvironmentTransitionError("REAL_LIVE requires explicit live approval at startup")

    def get_current_mode(self) -> ExecutionEnvironmentMode:
        with self._lock:
            return self._mode

    def snapshot(self) -> EnvironmentSnapshot:
        with self._lock:
            return EnvironmentSnapshot(self._mode, self._version, self._changed_at, self._changed_by)

    def is_skill_allowed(self, skill_name: str) -> bool:
        with self._lock:
            return skill_name in self.ALLOWED_SKILLS.get(self._mode, frozenset())

    def assert_skill_allowed(self, skill_name: str) -> None:
        if not self.is_skill_allowed(skill_name):
            raise EnvironmentTransitionError(
                f"skill '{skill_name}' is forbidden in mode {self.get_current_mode().value}"
            )

    def set_mode(self, mode: ExecutionEnvironmentMode, auth_token: str, actor: str = "operator") -> bool:
        if not isinstance(mode, ExecutionEnvironmentMode):
            raise ValueError("invalid execution mode")
        if not self._authorized(auth_token):
            raise EnvironmentTransitionError("environment transition authorization failed")
        if mode is ExecutionEnvironmentMode.REAL_LIVE:
            if self.live_approval_gate is None:
                raise EnvironmentTransitionError("REAL_LIVE requires LiveApprovalGate")
            self.live_approval_gate.require(mode)
        with self._lock:
            self._mode = mode
            self._version += 1
            self._changed_at = datetime.now(UTC)
            self._changed_by = actor
            return True

    def register_time_trigger(self, target_time: str, mode: ExecutionEnvironmentMode) -> bool:
        datetime.fromisoformat(target_time.replace("Z", "+00:00"))
        self._time_triggers[target_time] = mode
        return True

    def register_kpi_trigger(self, metric: str, threshold: float, mode: ExecutionEnvironmentMode) -> bool:
        if not metric or not isinstance(threshold, (int, float)):
            raise ValueError("invalid KPI trigger")
        self._kpi_triggers[metric] = (float(threshold), mode)
        return True

    def evaluate_kpi(self, metric: str, value: float) -> ExecutionEnvironmentMode | None:
        trigger = self._kpi_triggers.get(metric)
        if trigger and value >= trigger[0]:
            return trigger[1]
        return None

    def _authorized(self, token: str) -> bool:
        if not self.transition_secret or not token:
            return False
        expected = hmac.new(self.transition_secret.encode(), b"environment-transition", hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, token)
