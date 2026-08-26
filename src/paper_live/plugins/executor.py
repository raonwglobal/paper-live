from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable
from .sandbox import PluginSandbox
from .skill_registry import SkillRegistry, SkillRegistryError

class SkillExecutionError(RuntimeError):
    pass

@dataclass(frozen=True)
class ExecutionContext:
    plugin_id: str
    skill_id: str
    mode: str

class PluginSkillExecutor:
    """Executes only registered, explicitly bound skill callables.

    Arbitrary module import and subprocess execution are intentionally absent.
    A container executor can replace the callable backend without changing the registry contract.
    """
    def __init__(self, registry: SkillRegistry, sandbox: PluginSandbox | None = None):
        self.registry = registry
        self.sandbox = sandbox or PluginSandbox()
        self._handlers: dict[str, Callable[..., Any]] = {}

    def bind(self, skill_id: str, handler: Callable[..., Any]) -> None:
        self.registry.resolve(skill_id)
        self._handlers[skill_id] = handler

    def execute(self, skill_id: str, *, mode: str, **kwargs: Any) -> Any:
        skill = self.registry.resolve(skill_id)
        handler = self._handlers.get(skill_id)
        if handler is None:
            raise SkillExecutionError(f"skill has no approved handler: {skill_id}")
        if mode == "REAL_LIVE":
            raise SkillExecutionError("plugin skills cannot directly execute REAL_LIVE operations")
        try:
            return handler(**kwargs)
        except Exception as exc:
            raise SkillExecutionError(f"skill execution failed: {skill.skill_id}") from exc
