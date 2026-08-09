"""Project Instructions - Auto-load CLAUDE.md / .sago/instructions.md.

Like CLAUDE.md in Claude Code, this loads project-level instructions
that guide the agent's behavior for specific codebases.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


# File names to search for (in order of priority)
INSTRUCTION_FILES = [
    "CLAUDE.md",
    ".claude/instructions.md",
    ".sago/instructions.md",
    ".sago/rules.md",
    "AGENTS.md",
    ".cursorrules",
    ".windsurfrules",
    ".github/copilot-instructions.md",
]

# Max size to load (avoid huge files)
MAX_INSTRUCTION_SIZE = 10_000  # characters


class ProjectInstructions:
    """Loads and manages project-level instructions from files."""

    def __init__(self, cwd: str | None = None) -> None:
        self.cwd = cwd or os.getcwd()
        self._instructions: str | None = None
        self._metadata: dict[str, Any] = {}

    def _find_instruction_file(self) -> Path | None:
        """Find the first existing instruction file."""
        for filename in INSTRUCTION_FILES:
            path = Path(self.cwd) / filename
            if path.exists() and path.is_file():
                return path
        return None

    def load(self) -> str:
        """Load project instructions from file."""
        if self._instructions is not None:
            return self._instructions

        path = self._find_instruction_file()
        if path is None:
            self._instructions = ""
            return ""

        try:
            content = path.read_text(encoding="utf-8")
            # Truncate if too large
            if len(content) > MAX_INSTRUCTION_SIZE:
                content = content[:MAX_INSTRUCTION_SIZE] + "\n\n[...truncated...]"
            self._instructions = content
            self._metadata = {
                "file": str(path),
                "size": len(content),
                "line_count": content.count("\n") + 1,
            }
        except Exception:
            self._instructions = ""

        return self._instructions

    def get_metadata(self) -> dict[str, Any]:
        """Get metadata about loaded instructions."""
        if self._instructions is None:
            self.load()
        return self._metadata

    def get_for_prompt(self) -> str:
        """Get instructions formatted for injection into system prompt."""
        instructions = self.load()
        if not instructions:
            return ""

        return (
            f"\n\n=== PROJECT INSTRUCTIONS ===\n"
            f"Follow these project-specific rules:\n"
            f"{instructions}\n"
            f"=== END PROJECT INSTRUCTIONS ==="
        )

    def get_for_context(self) -> str:
        """Get instructions as context info."""
        instructions = self.load()
        if not instructions:
            return ""

        meta = self.get_metadata()
        return (
            f"Project instructions loaded from {meta.get('file', 'unknown')} "
            f"({meta.get('line_count', 0)} lines)"
        )

    @staticmethod
    def create_default(project_type: str = "python", path: str = ".") -> Path:
        """Create a default instruction file for a project."""
        instruction_file = Path(path) / ".sago" / "instructions.md"
        instruction_file.parent.mkdir(parents=True, exist_ok=True)

        defaults = {
            "python": (
                "# Project Instructions\n\n"
                "## Code Style\n"
                "- Follow PEP 8\n"
                "- Use type hints\n"
                "- Use f-strings for formatting\n"
                "- Keep functions under 30 lines\n\n"
                "## Testing\n"
                "- Write tests for all new functions\n"
                "- Use pytest fixtures\n"
                "- Aim for >80% coverage\n\n"
                "## Structure\n"
                "- Single responsibility per module\n"
                "- Use dataclasses for data structures\n"
                "- Prefer composition over inheritance\n"
            ),
            "javascript": (
                "# Project Instructions\n\n"
                "## Code Style\n"
                "- Use ESLint + Prettier\n"
                "- Prefer const/let over var\n"
                "- Use async/await over .then()\n"
                "- Use template literals\n\n"
                "## Testing\n"
                "- Write tests for all new functions\n"
                "- Use Jest for testing\n"
                "- Mock external dependencies\n"
            ),
        }

        content = defaults.get(project_type, defaults["python"])
        instruction_file.write_text(content, encoding="utf-8")
        return instruction_file


def get_project_instructions(cwd: str | None = None) -> ProjectInstructions:
    """Get project instructions instance."""
    return ProjectInstructions(cwd)
