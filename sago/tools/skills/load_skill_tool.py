"""Load Skill Tool - Lazily load a SKILL.md resource on demand."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from sago.skills.loader import SkillLoader
from sago.tools.base import BaseTool

logger = logging.getLogger("sago.tools.skills.load_skill_tool")


class LoadSkillArgs(BaseModel):
    name: str = Field(description="Skill name to load")
    extra_dirs: list[str] = Field(default_factory=list, description="Extra skill directories")


class LoadSkillTool(BaseTool):
    name = "load_skill"
    description = "PREFER for skills: lazily load a SKILL.md resource on demand (no eager loading)."
    args_model = LoadSkillArgs

    def _run(self, name: str, extra_dirs: list[str] | None = None, **kwargs: Any) -> str:
        dirs = [Path(d) for d in (extra_dirs or [])]
        skills = SkillLoader.discover_skills(extra_dirs=dirs)
        skill = skills.get(name.lower())
        if not skill:
            return f"Skill '{name}' not found. Available: {', '.join(sorted(skills)) or '(none)'}"
        return skill.to_prompt_context()
