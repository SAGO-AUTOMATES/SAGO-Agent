"""Custom Skills Loader and Runtime

Discovers, parses, and activates custom skills defined in SKILL.md documents
or Python modules across workspace and user directories.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sago.paths import get_sago_home
from sago.utils.safe import log_exception

logger = logging.getLogger(__name__)


@dataclass
class CustomSkill:
    """A custom skill defined by markdown or configuration."""

    name: str
    description: str
    tools: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    instructions: str = ""
    source_path: Path | None = None
    tags: list[str] = field(default_factory=list)

    def to_prompt_context(self) -> str:
        """Format skill into structured prompt instructions."""
        lines = [
            f"### Active Skill: {self.name}",
            f"**Objective**: {self.description}",
        ]
        if self.tools:
            lines.append(f"**Recommended Tools**: {', '.join(self.tools)}")
        if self.steps:
            lines.append("**Execution Workflow**:")
            for i, step in enumerate(self.steps, 1):
                lines.append(f"  {i}. {step}")
        if self.instructions:
            lines.append(f"\n**Detailed Instructions**:\n{self.instructions}")
        return "\n".join(lines)


class SkillLoader:
    """Discovers and parses custom skills from disk."""

    @classmethod
    def parse_markdown_skill(cls, skill_file: Path) -> CustomSkill | None:
        """Parse a SKILL.md file with YAML frontmatter or standard markdown headings."""
        try:
            content = skill_file.read_text(encoding="utf-8")
            metadata: dict[str, Any] = {}
            body = content

            # Check for YAML frontmatter
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    import yaml

                    try:
                        metadata = yaml.safe_load(parts[1]) or {}
                    except Exception as e:
                        log_exception(e, "Failed to parse YAML frontmatter")
                    body = parts[2].strip()

            name = metadata.get("name") or skill_file.parent.name or skill_file.stem
            description = metadata.get("description", "")
            tools = metadata.get("tools", [])
            steps = metadata.get("steps", [])
            tags = metadata.get("tags", [])

            # Extract fallback description if empty
            if not description and body:
                first_line = [line.strip() for line in body.splitlines() if line.strip()]
                if first_line:
                    description = first_line[0].lstrip("#").strip()

            return CustomSkill(
                name=name,
                description=description,
                tools=tools if isinstance(tools, list) else [str(tools)],
                steps=steps if isinstance(steps, list) else [str(steps)],
                instructions=body,
                source_path=skill_file,
                tags=tags if isinstance(tags, list) else [str(tags)],
            )
        except Exception as exc:
            logger.warning("Failed to parse skill at %s: %s", skill_file, exc)
            return None

    @classmethod
    def discover_skills(cls, extra_dirs: list[Path] | None = None) -> dict[str, CustomSkill]:
        """Discover custom skills across workspace and user directories."""
        skills: dict[str, CustomSkill] = {}
        search_dirs = [
            get_sago_home() / "skills",
            Path.cwd() / ".sago" / "skills",
            Path.cwd() / "skills",
        ]
        if extra_dirs:
            search_dirs.extend(extra_dirs)

        for s_dir in search_dirs:
            if not s_dir.exists() or not s_dir.is_dir():
                continue

            # Check for SKILL.md in subdirectories
            for skill_md in s_dir.glob("**/SKILL.md"):
                skill = cls.parse_markdown_skill(skill_md)
                if skill:
                    skills[skill.name.lower()] = skill

            # Check for direct .md files in skills directory
            for md_file in s_dir.glob("*.md"):
                if md_file.name.upper() == "README.MD":
                    continue
                skill = cls.parse_markdown_skill(md_file)
                if skill:
                    skills[skill.name.lower()] = skill

        return skills
