from __future__ import annotations

from dataclasses import dataclass
from threading import RLock


class SkillRegistryError(RuntimeError):
    pass


@dataclass(frozen=True)
class RegisteredSkill:
    skill_id: str
    plugin_id: str
    version: str
    entrypoint: str


class SkillRegistry:
    def __init__(self):
        self._skills: dict[str, RegisteredSkill] = {}
        self._lock = RLock()

    def register(self, skill: RegisteredSkill) -> None:
        with self._lock:
            existing = self._skills.get(skill.skill_id)
            if existing and existing.plugin_id != skill.plugin_id:
                raise SkillRegistryError(f"skill id collision: {skill.skill_id}")
            self._skills[skill.skill_id] = skill

    def unregister_plugin(self, plugin_id: str) -> None:
        with self._lock:
            for key in [k for k, v in self._skills.items() if v.plugin_id == plugin_id]:
                del self._skills[key]

    def resolve(self, skill_id: str) -> RegisteredSkill:
        with self._lock:
            try:
                return self._skills[skill_id]
            except KeyError as exc:
                raise SkillRegistryError(f"unknown skill: {skill_id}") from exc

    def list(self) -> tuple[RegisteredSkill, ...]:
        with self._lock:
            return tuple(self._skills.values())
