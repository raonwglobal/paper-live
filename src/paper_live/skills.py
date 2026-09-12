from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .environment import EnvironmentController, EnvironmentTransitionError


@dataclass(frozen=True)
class Skill:
    name: str
    handler: Callable[..., Any]


class SkillRegistry:
    def __init__(self, controller: EnvironmentController):
        self.controller = controller
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        if skill.name in self._skills:
            raise ValueError(f"skill already registered: {skill.name}")
        self._skills[skill.name] = skill

    def invoke(self, name: str, **kwargs: Any) -> Any:
        self.controller.assert_skill_allowed(name)
        skill = self._skills.get(name)
        if skill is None:
            raise EnvironmentTransitionError(f"skill is not registered: {name}")
        return skill.handler(**kwargs)

    def available(self) -> tuple[str, ...]:
        return tuple(sorted(self._skills))
