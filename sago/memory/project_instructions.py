"""Project Instructions - Auto-load all .md files from project root.

Scans for CLAUDE.md, README.md, AGENTS.md, CONTRIBUTING.md, and all other
.md files in the project root, merging them into a single instruction set.
Also loads .sago/instructions.md, .cursorrules, .windsurfrules.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("sago.memory.instructions")

# Priority files loaded first (in order)
PRIORITY_FILES = [
    "CLAUDE.md",
    ".sago/instructions.md",
    "AGENTS.md",
    "README.md",
    "CONTRIBUTING.md",
    "ARCHITECTURE.md",
    "DESIGN.md",
    ".cursorrules",
    ".windsurfrules",
    ".github/copilot-instructions.md",
]

# Max total size for all instruction files combined
MAX_TOTAL_INSTRUCTION_SIZE = 30_000  # characters

# Max individual file size
MAX_SINGLE_FILE_SIZE = 15_000  # characters

# Directories to skip when scanning for .md files
SKIP_DIRS = {
    "node_modules",
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "target",
    "vendor",
    "dist",
    "build",
    ".tox",
    ".mypy_cache",
}


class ProjectInstructions:
    """Loads and manages project-level instructions from all .md files."""

    def __init__(self, cwd: str | None = None) -> None:
        self.cwd = cwd or os.getcwd()
        self._instructions: str | None = None
        self._metadata: dict[str, Any] = {}

    def _find_all_instruction_files(self) -> list[tuple[str, Path]]:
        """Find all .md instruction files in priority order.

        Returns list of (source_label, path) tuples.
        """
        results: list[tuple[str, Path]] = []
        seen: set[str] = set()
        work_dir = Path(self.cwd)

        # 1. Load priority files first
        for filename in PRIORITY_FILES:
            path = work_dir / filename
            if path.exists() and path.is_file():
                results.append((filename, path))
                seen.add(str(path))

        # 2. Scan for any other .md files in project root (not recursive)
        try:
            for path in sorted(work_dir.iterdir()):
                if (
                    path.suffix.lower() == ".md"
                    and path.is_file()
                    and str(path) not in seen
                    and not path.name.startswith(".")
                ):
                    results.append((path.name, path))
                    seen.add(str(path))
        except FileNotFoundError:
            pass

        # 3. Scan .sago/ directory for additional instructions
        sago_dir = work_dir / ".sago"
        if sago_dir.exists() and sago_dir.is_dir():
            for path in sorted(sago_dir.iterdir()):
                if path.suffix.lower() == ".md" and path.is_file() and str(path) not in seen:
                    results.append((f".sago/{path.name}", path))
                    seen.add(str(path))

        return results

    def load(self) -> str:
        """Load all project instructions from found files."""
        if self._instructions is not None:
            return self._instructions

        files = self._find_all_instruction_files()
        if not files:
            self._instructions = ""
            self._metadata = {"files": [], "total_size": 0}
            logger.debug("No instruction files found in %s", self.cwd)
            return ""

        logger.debug("Found %d instruction files in %s", len(files), self.cwd)

        parts: list[str] = []
        loaded_files: list[dict[str, Any]] = []
        total_size = 0

        for source_label, path in files:
            if total_size >= MAX_TOTAL_INSTRUCTION_SIZE:
                break

            try:
                content = path.read_text(encoding="utf-8")
                # Truncate individual files if too large
                if len(content) > MAX_SINGLE_FILE_SIZE:
                    content = content[:MAX_SINGLE_FILE_SIZE] + "\n\n[...truncated...]"

                # Skip files that are mostly not instructions (e.g., huge READMEs with images)
                # Heuristic: if file has < 10% instructional content, skip it
                instructional_keywords = [
                    "should",
                    "must",
                    "do not",
                    "never",
                    "always",
                    "follow",
                    "use ",
                    "avoid ",
                    "prefer ",
                    "require",
                    "rule",
                    "guideline",
                    "convention",
                    "standard",
                    "setup",
                    "install",
                    "configure",
                    "test",
                ]
                content_lower = content.lower()
                keyword_count = sum(1 for kw in instructional_keywords if kw in content_lower)
                line_count = content.count("\n") + 1
                keyword_ratio = keyword_count / max(line_count, 1)

                # Include if it has enough instructional content OR is a priority file
                is_priority = source_label in PRIORITY_FILES or source_label.startswith(".sago/")
                if keyword_ratio < 0.02 and not is_priority and line_count > 50:
                    continue  # Skip non-instructional files (e.g., changelogs)

                parts.append(f"--- {source_label} ---\n{content}")
                total_size += len(content)
                loaded_files.append(
                    {
                        "file": str(path),
                        "source": source_label,
                        "size": len(content),
                        "line_count": line_count,
                    }
                )
            except Exception:
                continue

        combined = "\n\n".join(parts)

        # Final truncation if combined is too large
        if len(combined) > MAX_TOTAL_INSTRUCTION_SIZE:
            combined = (
                combined[:MAX_TOTAL_INSTRUCTION_SIZE]
                + "\n\n[...additional instructions truncated...]"
            )

        self._instructions = combined
        self._metadata = {
            "files": loaded_files,
            "total_size": total_size,
            "file_count": len(loaded_files),
        }

        logger.info(
            "Loaded %d instruction files (%d chars) from %s",
            len(loaded_files),
            total_size,
            self.cwd,
        )
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

        meta = self.get_metadata()
        file_count = meta.get("file_count", 0)
        total_size = meta.get("total_size", 0)

        logger.debug(
            "Formatting instructions for prompt (%d files, %d chars)", file_count, total_size
        )
        return (
            f"\n\n=== PROJECT INSTRUCTIONS ({file_count} files, {total_size} chars) ===\n"
            f"Follow these project-specific rules:\n"
            f"{instructions}\n"
            f"=== END PROJECT INSTRUCTIONS ==="
        )

    def get_for_context(self) -> str:
        """Get instructions as context info."""
        if self._instructions is None:
            self.load()
        meta = self.get_metadata()
        files = meta.get("files", [])
        if not files:
            return "No project instructions found."
        file_names = [f["source"] for f in files]
        return f"Project instructions loaded from {len(files)} files: {', '.join(file_names)}"

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
