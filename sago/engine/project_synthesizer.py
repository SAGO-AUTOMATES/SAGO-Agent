"""Project Synthesis Engine - Multi-phase topological generation for 30-50+ file projects.

Implements contract-first architecture:
Phase 1: Architecture & Directory DAG Planning
Phase 2: Types, Configs & Contracts (Contract Locking)
Phase 3: Database Models & Core Utilities
Phase 4: Business Logic & Services
Phase 5: API Layer, Controllers & CLI
Phase 6: Frontend / Client Adapters (if applicable)
Phase 7: Test Suite & Fixtures
Phase 8: Automated Verification & Self-Healing
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FileSpec:
    """Specification of a file in the project synthesis plan."""

    path: str
    phase: int
    purpose: str
    dependencies: list[str] = field(default_factory=list)
    key_symbols: list[str] = field(default_factory=list)
    status: str = "pending"  # "pending", "in_progress", "completed", "failed"
    created_at: float = 0.0
    error: str | None = None


@dataclass
class SynthesisPlan:
    """Full architectural synthesis plan for multi-file generation."""

    project_name: str
    root_dir: str
    description: str
    tech_stack: list[str]
    files: list[FileSpec] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_name": self.project_name,
            "root_dir": self.root_dir,
            "description": self.description,
            "tech_stack": self.tech_stack,
            "files": [
                {
                    "path": f.path,
                    "phase": f.phase,
                    "purpose": f.purpose,
                    "dependencies": f.dependencies,
                    "key_symbols": f.key_symbols,
                    "status": f.status,
                }
                for f in self.files
            ],
        }


class ProjectSynthesizer:
    """Orchestrates topological generation of complex codebases."""

    def __init__(
        self,
        root_dir: str | Path | None = None,
        on_progress: Callable[[str, int, int], None] | None = None,
    ) -> None:
        self.root_dir = Path(root_dir) if root_dir else Path.cwd()
        self.on_progress = on_progress

    def plan_project(
        self,
        project_description: str,
        tech_stack: list[str] | None = None,
    ) -> SynthesisPlan:
        """Create a structured synthesis plan with phased file dependencies."""
        stack = tech_stack or ["python", "pytest"]
        logger.info("Planning project: name=%s, tech_stack=%s", self.root_dir.name, stack)
        logger.debug("Project description: %.200s", project_description)
        plan = SynthesisPlan(
            project_name=self.root_dir.name,
            root_dir=str(self.root_dir),
            description=project_description,
            tech_stack=stack,
        )
        return plan

    def save_plan(self, plan: SynthesisPlan, file_name: str = ".sago_plan.json") -> Path:
        target = self.root_dir / file_name
        logger.info("Saving synthesis plan: files=%d, target=%s", len(plan.files), target)
        target.write_text(json.dumps(plan.to_dict(), indent=2), encoding="utf-8")
        return target

    def load_plan(self, file_name: str = ".sago_plan.json") -> SynthesisPlan | None:
        target = self.root_dir / file_name
        if not target.exists():
            logger.debug("No synthesis plan found at %s", target)
            return None
        try:
            logger.info("Loading synthesis plan from %s", target)
            data = json.loads(target.read_text(encoding="utf-8"))
            files = [
                FileSpec(
                    path=f["path"],
                    phase=f["phase"],
                    purpose=f["purpose"],
                    dependencies=f.get("dependencies", []),
                    key_symbols=f.get("key_symbols", []),
                    status=f.get("status", "pending"),
                )
                for f in data.get("files", [])
            ]
            return SynthesisPlan(
                project_name=data["project_name"],
                root_dir=data["root_dir"],
                description=data["description"],
                tech_stack=data.get("tech_stack", []),
                files=files,
            )
        except Exception as e:
            logger.error(f"Failed to load synthesis plan: {e}")
            return None
