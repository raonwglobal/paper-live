from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ..environment import EnvironmentController, ExecutionEnvironmentMode
from ..execution import ExecutionGateway, Fill, PaperOrderRequest
from ..risk import RiskGuardian
from .executor import PluginSkillExecutor, SkillExecutionError
from .lifecycle import PluginLifecycle, PluginLifecycleError, PluginState
from .policy import PluginExecutionPolicy
from .skill_registry import SkillRegistry


@dataclass(frozen=True)
class PluginExecutionRequest:
    plugin_id: str
    skill_id: str
    mode: ExecutionEnvironmentMode


class PluginRuntime:
    """Application-level integration point for verified plugin skills.

    Plugins can analyze/produce an order request, but every paper/backtest order
    passes through the core RiskGuardian and ExecutionGateway. Plugins have no
    direct broker path and REAL_LIVE is rejected before a handler is invoked.
    """

    def __init__(
        self,
        lifecycle: PluginLifecycle,
        registry: SkillRegistry,
        executor: PluginSkillExecutor,
        environment: EnvironmentController,
        risk: RiskGuardian,
        execution: ExecutionGateway,
        policy: PluginExecutionPolicy | None = None,
    ):
        self.lifecycle = lifecycle
        self.registry = registry
        self.executor = executor
        self.environment = environment
        self.risk = risk
        self.execution = execution
        self.policy = policy or PluginExecutionPolicy()

    def invoke(self, request: PluginExecutionRequest, **kwargs: Any) -> Any:
        record = self.lifecycle.get(request.plugin_id)
        if record.state is not PluginState.ENABLED:
            raise PluginLifecycleError(f"plugin is not enabled: {request.plugin_id}")
        skill = self.registry.resolve(request.skill_id)
        if skill.plugin_id != request.plugin_id:
            raise SkillExecutionError("skill does not belong to requested plugin")
        actual_mode = self.environment.get_current_mode()
        if request.mode.value != actual_mode.value:
            raise PermissionError("plugin requested mode does not match environment")
        self.policy.check(request.mode.value)
        return self.executor.execute(request.skill_id, mode=request.mode.value, **kwargs)

    def submit_paper_order(
        self,
        request: PluginExecutionRequest,
        order: PaperOrderRequest,
        reference_price: Decimal,
        available_quantity: Decimal | None = None,
    ) -> Fill:
        if request.mode is ExecutionEnvironmentMode.REAL_LIVE:
            raise PermissionError("plugin trading cannot execute REAL_LIVE")
        if self.environment.get_current_mode() is not request.mode:
            raise PermissionError("environment mode changed before order execution")
        self.policy.check(request.mode.value)
        self.risk.approve(order, reference_price)
        return self.execution.execute(order, reference_price, available_quantity)
