from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import hmac
import threading
from typing import Dict, FrozenSet, Optional


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
    """Central fail-closed policy boundary for execution skills.

    This class deliberately does not contain broker credentials and cannot
    execute orders. It only decides which skill classes may be invoked.
    """

    initial_mode: ExecutionEnvironmentMode = ExecutionEnvironmentMode.PAPER_SANDBOX
    transition_secret: Optional[str] = None
    _mode: ExecutionEnvironmentMode = field(init=False)
    _version: int = field(default=0, init=False)
    _changed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc), init=False)
    _changed_by: str = field(default="system", init=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)
    _time_triggers: Dict[str, ExecutionEnvironmentMode] = field(default_factory=dict, init=False)
    _kpi_triggers: Dict[str, tuple[float, ExecutionEnvironmentMode]] = field(default_factory=dict, init=False)

    ALLOWED_SKILLS: Dict[ExecutionEnvironmentMode, FrozenSet[str]] = field(default_factory=lambda: {
        ExecutionEnvironmentMode.PAPER_SANDBOX: frozenset({"skill-virtual-matching-engine", "skill-market-data"}),
        ExecutionEnvironmentMode.VIRTUAL_BACKTEST: frozenset({"skill-virtual-matching-engine", "skill-historical-data"}),
        ExecutionEnvironmentMode.REAL_LIVE: frozenset({"skill-toss-broker", "skill-kb-broker", "skill-market-data", "skill-risk-circuit-breaker"}),
    }, init=False)

    def __post_init__(self) -> None:
        self._mode = self.initial_mode

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
        with self._lock:
            if mode == ExecutionEnvironmentMode.REAL_LIVE and self._mode != ExecutionEnvironmentMode.REAL_LIVE:
                # Live promotion is intentionally explicit and auditable.
                pass
            self._mode = mode
            self._version += 1
            self._changed_at = datetime.now(timezone.utc)
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

    def evaluate_kpi(self, metric: str, value: float) -> Optional[ExecutionEnvironmentMode]:
        trigger = self._kpi_triggers.get(metric)
        if trigger and value >= trigger[0]:
            return trigger[1]
        return None

    def _authorized(self, token: str) -> bool:
        if not self.transition_secret or not token:
            return False
        expected = hmac.new(self.transition_secret.encode(), b"environment-transition", hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, token)
