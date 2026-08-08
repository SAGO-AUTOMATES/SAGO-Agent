"""Skills System

Reusable agent capabilities that can be composed and extended.
Skills provide higher-level abstractions over tools.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Skill:
    """A reusable agent skill."""
    name: str
    description: str
    tools: list[str]
    steps: list[str]
    examples: list[str] = field(default_factory=list)
    handler: Callable[..., Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "tools": self.tools,
            "steps": self.steps,
            "examples": self.examples,
        }


# Pre-built skills
SKILLS: dict[str, Skill] = {
    "code_review": Skill(
        name="code_review",
        description="Review code for quality, security, and best practices",
        tools=["read_file", "grep_content", "code_analyzer", "linter"],
        steps=[
            "Read the target files",
            "Analyze code structure and complexity",
            "Check for security issues",
            "Run linter for style issues",
            "Generate review report",
        ],
        examples=[
            "Review the authentication module",
            "Check this PR for security issues",
            "Analyze code quality in src/",
        ],
    ),
    "bug_fix": Skill(
        name="bug_fix",
        description="Debug and fix bugs systematically",
        tools=["read_file", "grep_content", "debugger", "test_runner", "edit_file"],
        steps=[
            "Understand the error description",
            "Locate relevant code files",
            "Analyze the root cause",
            "Implement the fix",
            "Run tests to verify",
        ],
        examples=[
            "Fix the authentication bug",
            "Resolve the memory leak",
            "Fix failing tests",
        ],
    ),
    "feature_impl": Skill(
        name="feature_impl",
        description="Implement new features end-to-end",
        tools=["read_file", "write_file", "edit_file", "code_analyzer", "test_runner"],
        steps=[
            "Understand requirements",
            "Design the implementation",
            "Create necessary files",
            "Implement the feature",
            "Write tests",
            "Update documentation",
        ],
        examples=[
            "Add user authentication",
            "Implement API endpoint",
            "Create new component",
        ],
    ),
    "refactor": Skill(
        name="refactor",
        description="Refactor code for better quality",
        tools=["read_file", "edit_file", "code_analyzer", "linter", "test_runner"],
        steps=[
            "Analyze current code structure",
            "Identify refactoring opportunities",
            "Implement changes incrementally",
            "Run tests after each change",
            "Verify no regressions",
        ],
        examples=[
            "Refactor the database layer",
            "Clean up the API module",
            "Improve code organization",
        ],
    ),
    "deploy": Skill(
        name="deploy",
        description="Deploy applications safely",
        tools=["execute_shell", "git_ops", "docker_ops"],
        steps=[
            "Verify tests pass",
            "Build the application",
            "Create deployment artifacts",
            "Deploy to target environment",
            "Verify deployment health",
        ],
        examples=[
            "Deploy to production",
            "Release version 2.0",
            "Rollback deployment",
        ],
    ),
    "security_audit": Skill(
        name="security_audit",
        description="Perform security audit",
        tools=["read_file", "grep_content", "code_analyzer", "linter"],
        steps=[
            "Scan for common vulnerabilities",
            "Check dependency security",
            "Review authentication code",
            "Analyze permission handling",
            "Generate security report",
        ],
        examples=[
            "Audit the authentication system",
            "Check for SQL injection",
            "Review API security",
        ],
    ),
    "documentation": Skill(
        name="documentation",
        description="Generate and update documentation",
        tools=["read_file", "write_file", "code_analyzer"],
        steps=[
            "Analyze code structure",
            "Extract public APIs",
            "Generate documentation",
            "Update README",
            "Create examples",
        ],
        examples=[
            "Document the API",
            "Update the README",
            "Create usage examples",
        ],
    ),
    "testing": Skill(
        name="testing",
        description="Write and run tests",
        tools=["read_file", "write_file", "test_runner", "code_analyzer"],
        steps=[
            "Analyze code to test",
            "Identify test cases",
            "Write unit tests",
            "Write integration tests",
            "Run test suite",
        ],
        examples=[
            "Write unit tests for the API",
            "Add integration tests",
            "Improve test coverage",
        ],
    ),
    "performance": Skill(
        name="performance",
        description="Optimize performance",
        tools=["read_file", "edit_file", "code_analyzer", "profiler"],
        steps=[
            "Profile current performance",
            "Identify bottlenecks",
            "Implement optimizations",
            "Measure improvements",
            "Document changes",
        ],
        examples=[
            "Optimize database queries",
            "Improve API response time",
            "Reduce memory usage",
        ],
    ),
    "data_pipeline": Skill(
        name="data_pipeline",
        description="Build data processing pipelines",
        tools=["read_file", "write_file", "execute_shell", "database_query"],
        steps=[
            "Understand data sources",
            "Design pipeline architecture",
            "Implement data ingestion",
            "Add transformation logic",
            "Set up output destinations",
        ],
        examples=[
            "Build ETL pipeline",
            "Process log data",
            "Migrate database",
        ],
    ),
}


class SkillRegistry:
    """Registry for managing skills."""

    def __init__(self) -> None:
        self.skills: dict[str, Skill] = dict(SKILLS)

    def get_skill(self, name: str) -> Skill | None:
        """Get a skill by name."""
        return self.skills.get(name)

    def list_skills(self) -> list[dict[str, Any]]:
        """List all available skills."""
        return [skill.to_dict() for skill in self.skills.values()]

    def find_skills_for_task(self, task: str) -> list[Skill]:
        """Find skills that match a task description."""
        task_lower = task.lower()
        matches = []
        for skill in self.skills.values():
            # Check if any example matches
            for example in skill.examples:
                if any(word in example.lower() for word in task_lower.split()):
                    matches.append(skill)
                    break
        return matches

    def register_skill(self, skill: Skill) -> None:
        """Register a custom skill."""
        self.skills[skill.name] = skill

    def get_tools_for_skill(self, skill_name: str) -> list[str]:
        """Get tools needed for a skill."""
        skill = self.skills.get(skill_name)
        return skill.tools if skill else []


# Global registry
_registry: SkillRegistry | None = None


def get_skill_registry() -> SkillRegistry:
    """Get global skill registry."""
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
    return _registry
