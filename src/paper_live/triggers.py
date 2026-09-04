from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from .environment import EnvironmentController, ExecutionEnvironmentMode


@dataclass(frozen=True)
class TriggerDecision:
    target_mode: ExecutionEnvironmentMode | None
    reason: str
    requires_human_approval: bool


class TriggerEvaluator:
    """Evaluates registered trigger conditions; never promotes to REAL_LIVE by itself."""

    def __init__(self, controller: EnvironmentController):
        self.controller = controller

    def evaluate_kpi(self, metric: str, value: float) -> TriggerDecision:
        target = self.controller.evaluate_kpi(metric, value)
        if target is None:
            return TriggerDecision(None, "KPI threshold not met", False)
        return TriggerDecision(target, f"KPI {metric} reached {value}", target is ExecutionEnvironmentMode.REAL_LIVE)

    def evaluate_time(self, now: datetime | None = None) -> TriggerDecision:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        for target_time, mode in list(self.controller._time_triggers.items()):
            target = datetime.fromisoformat(target_time.replace("Z", "+00:00")).astimezone(UTC)
            if current >= target:
                return TriggerDecision(
                    mode, f"time trigger reached: {target.isoformat()}", mode is ExecutionEnvironmentMode.REAL_LIVE
                )
        return TriggerDecision(None, "time trigger not reached", False)
