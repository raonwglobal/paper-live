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
    def __init__(self, lifecycle: PluginLifecycle, registry: SkillRegistry,
                 executor: PluginSkillExecutor, environment: EnvironmentController,
                 risk: RiskGuardian, execution: ExecutionGateway,
                 policy: PluginExecutionPolicy | None = None):
        self.lifecycle = lifecycle
        self.registry = registry
        self.executor = executor
        self.environment = environment
        self.risk = risk
        self.execution = execution
        self.policy = policy or PluginExecutionPolicy()

    def invoke(self, request: PluginExecutionRequest, **kwargs: Any) -> Any:
        if request.mode is ExecutionEnvironmentMode.REAL_LIVE:
            raise PermissionError("plugin runtime refuses REAL_LIVE execution")
        self.environment.assert_skill_allowed("skill-plugin-lifecycle")
        record = self.lifecycle.get(request.plugin_id)
        if record is None or record.state is not PluginState.ACTIVE:
            raise PluginLifecycleError(f"plugin is not ACTIVE: {request.plugin_id}")
        self.policy.validate_runtime_call(record.manifest, request.skill_id)
        try:
            return self.executor.execute(request.plugin_id, request.skill_id, **kwargs)
        except SkillExecutionError:
            raise

    def submit_paper_order(self, request: PluginExecutionRequest, order: PaperOrderRequest,
                           reference_price: Decimal) -> Fill:
        if request.mode is ExecutionEnvironmentMode.REAL_LIVE:
            raise PermissionError("plugin runtime refuses REAL_LIVE execution")
        # Plugins may only propose; core risk + gateway own the fill path.
        self.risk.approve(order, reference_price)
        return self.execution.execute(order, reference_price)
