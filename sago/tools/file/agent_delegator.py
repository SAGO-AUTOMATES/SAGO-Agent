"""Agent Delegation System

Smart routing of tasks to appropriate agents based on:
- File types and languages
- Task content analysis
- Project structure
- Agent skills and capabilities
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool

# Language to agent mapping
LANGUAGE_AGENTS: dict[str, list[str]] = {
    "python": ["python-engineer", "backend-engineer", "data-engineer"],
    "javascript": ["frontend-engineer", "backend-engineer", "fullstack-engineer"],
    "typescript": ["frontend-engineer", "backend-engineer", "fullstack-engineer"],
    "java": ["java-engineer", "backend-engineer"],
    "go": ["go-engineer", "backend-engineer", "devops"],
    "rust": ["rust-engineer", "systems-engineer"],
    "cpp": ["cpp-engineer", "systems-engineer"],
    "c": ["c-engineer", "systems-engineer"],
    "ruby": ["ruby-engineer", "backend-engineer"],
    "php": ["php-engineer", "backend-engineer"],
    "swift": ["ios-engineer", "mobile-engineer"],
    "kotlin": ["android-engineer", "mobile-engineer"],
    "dart": ["flutter-engineer", "mobile-engineer"],
    "html": ["frontend-engineer", "ui-engineer"],
    "css": ["frontend-engineer", "ui-engineer", "css-engineer"],
    "scss": ["frontend-engineer", "ui-engineer", "css-engineer"],
    "sql": ["database-engineer", "backend-engineer"],
    "shell": ["devops", "sre-engineer"],
    "yaml": ["devops", "kubernetes-engineer"],
    "toml": ["devops"],
    "json": ["backend-engineer"],
}

# Category to agent mapping
CATEGORY_AGENTS: dict[str, list[str]] = {
    "frontend": ["frontend-engineer", "ui-engineer", "react-engineer", "vue-engineer"],
    "backend": ["backend-engineer", "fullstack-engineer"],
    "mobile": ["mobile-engineer", "ios-engineer", "android-engineer"],
    "data": ["data-engineer", "data-analyst", "ml-engineer"],
    "devops": ["devops", "sre-engineer", "kubernetes-engineer"],
    "testing": ["qa-engineer", "test-engineer", "automation-engineer"],
    "security": ["security-engineer", "appsec-engineer"],
    "documentation": ["technical-writer", "documentation-updater"],
    "config": ["devops", "platform-engineer"],
}

# Task keyword to agent mapping
TASK_AGENTS: dict[str, list[str]] = {
    "bug": ["debugger", "qa-engineer"],
    "error": ["debugger", "qa-engineer"],
    "test": ["qa-engineer", "test-engineer"],
    "deploy": ["devops", "sre-engineer", "release-engineer"],
    "security": ["security-engineer", "appsec-engineer"],
    "performance": ["performance-engineer", "sre-engineer"],
    "database": ["database-engineer", "data-engineer"],
    "api": ["backend-engineer", "api-engineer"],
    "ui": ["frontend-engineer", "ui-engineer"],
    "design": ["ui-engineer", "ux-engineer"],
    "refactor": ["software-engineer", "fullstack-engineer"],
    "optimize": ["performance-engineer", "sre-engineer"],
    "review": ["code-reviewer", "security-engineer"],
    "document": ["technical-writer"],
    "setup": ["devops", "platform-engineer"],
    "install": ["devops", "platform-engineer"],
    "configure": ["devops", "platform-engineer"],
    "migrate": ["data-engineer", "backend-engineer"],
    "integration": ["fullstack-engineer", "backend-engineer"],
}


@dataclass
class DelegationResult:
    """Result of agent delegation analysis."""

    recommended_agents: list[str]
    primary_agent: str
    confidence: float
    reason: str
    language: str | None = None
    category: str | None = None
    task_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommended_agents": self.recommended_agents,
            "primary_agent": self.primary_agent,
            "confidence": self.confidence,
            "reason": self.reason,
            "language": self.language,
            "category": self.category,
            "task_type": self.task_type,
        }


class AgentDelegator:
    """Smart agent delegation based on context."""

    def __init__(self) -> None:
        self._agent_cache: dict[str, Any] = {}

    def delegate(
        self,
        task: str,
        file_path: str | None = None,
        language: str | None = None,
        category: str | None = None,
    ) -> DelegationResult:
        """Delegate task to best agent(s)."""
        scores: dict[str, float] = {}
        reasons: list[str] = []

        # Score by language
        if language and language in LANGUAGE_AGENTS:
            for agent in LANGUAGE_AGENTS[language][:2]:
                scores[agent] = scores.get(agent, 0) + 0.4
            reasons.append(f"language:{language}")

        # Score by category
        if category and category in CATEGORY_AGENTS:
            for agent in CATEGORY_AGENTS[category][:2]:
                scores[agent] = scores.get(agent, 0) + 0.3
            reasons.append(f"category:{category}")

        # Score by task keywords
        task_lower = task.lower()
        for keyword, agents in TASK_AGENTS.items():
            if keyword in task_lower:
                for agent in agents[:2]:
                    scores[agent] = scores.get(agent, 0) + 0.5
                reasons.append(f"task:{keyword}")

        # If no scores, use defaults
        if not scores:
            scores = {"fullstack-engineer": 0.5}
            reasons.append("default")

        # Sort by score
        sorted_agents = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        recommended = [a[0] for a in sorted_agents[:5]]
        primary = sorted_agents[0][0]
        confidence = min(sorted_agents[0][1], 1.0)

        return DelegationResult(
            recommended_agents=recommended,
            primary_agent=primary,
            confidence=confidence,
            reason=" + ".join(reasons),
            language=language,
            category=category,
            task_type=self._detect_task_type(task),
        )

    def delegate_for_files(
        self,
        files: list[str],
        task: str = "",
    ) -> DelegationResult:
        """Delegate based on multiple files."""
        # Analyze file types
        languages: dict[str, int] = {}

        for f in files:
            # Extract language from extension
            ext = f.rsplit(".", 1)[-1] if "." in f else ""
            for lang, exts in {
                "python": ["py"],
                "javascript": ["js", "jsx"],
                "typescript": ["ts", "tsx"],
                "java": ["java"],
                "go": ["go"],
                "rust": ["rs"],
            }.items():
                if ext in exts:
                    languages[lang] = languages.get(lang, 0) + 1

        # Get dominant language
        dominant_lang = None
        if languages:
            best = max(languages.items(), key=lambda x: x[1])
            dominant_lang = best[0]

        return self.delegate(
            task=task or "analyze files",
            language=dominant_lang,
        )

    def _detect_task_type(self, task: str) -> str | None:
        """Detect task type from description."""
        task_lower = task.lower()
        for keyword in TASK_AGENTS:
            if keyword in task_lower:
                return keyword
        return None

    def get_agent_for_file(self, file_path: str) -> str | None:
        """Get the best agent for a specific file."""
        ext = file_path.rsplit(".", 1)[-1] if "." in file_path else ""

        # Map extension to language
        ext_map = {
            "py": "python",
            "js": "javascript",
            "ts": "typescript",
            "java": "java",
            "go": "go",
            "rs": "rust",
            "rb": "ruby",
            "php": "php",
            "swift": "swift",
            "kt": "kotlin",
        }

        language = ext_map.get(ext)
        if language and language in LANGUAGE_AGENTS:
            return LANGUAGE_AGENTS[language][0]
        return None

    def execute_delegated(
        self,
        task: str,
        file_path: str | None = None,
        language: str | None = None,
        category: str | None = None,
    ) -> dict[str, Any]:
        """Delegate and actually execute the task with the best agent."""
        result = self.delegate(task, file_path, language, category)
        agent_name = result.primary_agent

        try:
            import os

            from sago.engine.simple_executor import execute_agent_task

            api_key = os.environ.get("OPENROUTER_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
            if not api_key:
                return {
                    "delegated_to": agent_name,
                    "confidence": result.confidence,
                    "reason": result.reason,
                    "success": False,
                    "error": "No API key configured. Set OPENROUTER_API_KEY or OPENAI_API_KEY.",
                }

            # Use configured model, fallback to openrouter/free
            try:
                from sago.config.loader import get_config

                config = get_config()
                model = config.llm.model or "openrouter/free"
            except Exception:
                model = "openrouter/free"

            # Try configured model first, then free model as fallback
            models_to_try = [model]
            if model != "openrouter/free":
                models_to_try.append("openrouter/free")

            last_error = ""
            for try_model in models_to_try:
                try:
                    exec_result = execute_agent_task(
                        task=task,
                        agent_role=agent_name.replace("-", " ").title(),
                        api_key=api_key,
                        model=try_model,
                        max_tokens=4096,
                        max_iterations=5,
                    )
                    output = exec_result.get("output", "")
                    # Check for real response
                    if output and not output.startswith("Error:") and len(output.strip()) > 10:
                        return {
                            "delegated_to": agent_name,
                            "confidence": result.confidence,
                            "reason": result.reason,
                            "recommended_agents": result.recommended_agents,
                            "success": True,
                            "output": output,
                            "tool_calls": len(exec_result.get("tool_calls", [])),
                        }
                    last_error = output or "Empty response"
                except Exception as e:
                    last_error = str(e)
                    continue

            # All models failed
            return {
                "delegated_to": agent_name,
                "confidence": result.confidence,
                "reason": result.reason,
                "success": False,
                "error": f"Agent '{agent_name}' failed: {last_error}",
                "alternatives": [
                    "Run the task directly without agent delegation",
                    "Try a different agent",
                    "Check API key credits at https://openrouter.ai/settings/credits",
                ],
            }
        except Exception as e:
            return {
                "delegated_to": agent_name,
                "confidence": result.confidence,
                "reason": result.reason,
                "success": False,
                "error": str(e),
            }


# Singleton delegator
_delegator: AgentDelegator | None = None


def get_delegator() -> AgentDelegator:
    """Get singleton delegator."""
    global _delegator
    if _delegator is None:
        _delegator = AgentDelegator()
    return _delegator


def delegate_task(
    task: str,
    file_path: str | None = None,
    language: str | None = None,
) -> DelegationResult:
    """Quick task delegation."""
    return get_delegator().delegate(task, file_path, language)


class AgentDelegatorArgs(BaseModel):
    """Arguments for agent delegation."""

    task: str = Field(description="Task to delegate to the best agent")
    file_path: str = Field(default="", description="Optional file path for context")
    language: str = Field(default="", description="Optional programming language")


class AgentDelegatorTool(BaseTool):
    """Delegate tasks to the best-suited agent based on context."""

    name: str = "delegate_to_agent"
    description: str = (
        "Smartly delegate a task to the most appropriate agent based on "
        "file types, language, task keywords, and project context. "
        "Actually executes the task with the selected agent."
    )
    args_model: type[BaseModel] = AgentDelegatorArgs

    def _run(
        self,
        task: str,
        file_path: str = "",
        language: str = "",
        **kwargs: Any,
    ) -> str:
        import json

        delegator = get_delegator()
        result = delegator.execute_delegated(
            task=task,
            file_path=file_path or None,
            language=language or None,
        )
        return json.dumps(result, indent=2, default=str)[:5000]


def get_tool() -> type[AgentDelegatorTool]:
    """Get the tool class."""
    return AgentDelegatorTool
