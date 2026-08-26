from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from ..environment import EnvironmentController
from .executor import PluginSkillExecutor, SkillExecutionError
from .lifecycle import PluginLifecycle, PluginLifecycleError, PluginState
from .policy import PluginExecutionPolicy

@dataclass(frozen=True)
class PluginCall:
    plugin_id: str
    skill_id: str
    mode: str

class PluginExecutionGateway:
    """Single fail-closed entry point for plugin skill execution."""
    def __init__(self, lifecycle: PluginLifecycle, executor: PluginSkillExecutor,
                 policy: PluginExecutionPolicy | None = None,
                 environment: EnvironmentController | None = None):
        self.lifecycle = lifecycle
        self.executor = executor
        self.policy = policy or PluginExecutionPolicy()
        self.environment = environment

    def execute(self, call: PluginCall, **kwargs: Any) -> Any:
        record = self.lifecycle.get(call.plugin_id)
        if record.state is not PluginState.ENABLED:
            raise PluginLifecycleError(f"plugin is not enabled: {call.plugin_id}")
        skill = self.executor.registry.resolve(call.skill_id)
        if skill.plugin_id != call.plugin_id:
            raise SkillExecutionError("skill does not belong to requested plugin")
        self.policy.check(call.mode)
        if self.environment is not None and self.environment.get_current_mode().value != call.mode:
            raise PermissionError("plugin requested mode does not match environment")
        return self.executor.execute(call.skill_id, mode=call.mode, **kwargs)
