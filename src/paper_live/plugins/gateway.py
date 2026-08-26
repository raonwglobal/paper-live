from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable
from .executor import PluginSkillExecutor, SkillExecutionError
from .lifecycle import PluginLifecycle, PluginLifecycleError, PluginState
from .policy import PluginExecutionPolicy, PluginModeDenied

@dataclass(frozen=True)
class PluginCall:
    plugin_id: str
    skill_id: str
    mode: str

class PluginExecutionGateway:
    """Single entry point for plugin skill execution.

    The gateway is fail-closed: a plugin must be enabled and its mode must be
    allowed before the executor can invoke a registered handler. REAL_LIVE is
    intentionally excluded from the default policy and cannot be enabled by
    plugin metadata.
    """
    def __init__(self, lifecycle: PluginLifecycle, executor: PluginSkillExecutor,
                 policy: PluginExecutionPolicy | None = None):
        self.lifecycle = lifecycle
        self.executor = executor
        self.policy = policy or PluginExecutionPolicy()

    def execute(self, call: PluginCall, **kwargs: Any) -> Any:
        record = self.lifecycle.get(call.plugin_id)
        if record.state != PluginState.ENABLED:
            raise PluginLifecycleError(f"plugin is not enabled: {call.plugin_id}")
        skill = self.executor.registry.resolve(call.skill_id)
        if skill.plugin_id != call.plugin_id:
            raise SkillExecutionError("skill does not belong to requested plugin")
        self.policy.check(call.mode)
        return self.executor.execute(call.skill_id, mode=call.mode, **kwargs)
