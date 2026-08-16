"""Prompt Generator Tool - Generate and manage AI prompts.

Cross-platform prompt management and generation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class PromptGeneratorArgs(BaseModel):
    """Arguments for PromptGeneratorTool."""

    operation: Literal["generate", "list", "save", "load", "template"] = Field(
        description="Operation to perform"
    )
    name: str | None = Field(default=None, description="Prompt name")
    content: str | None = Field(default=None, description="Prompt content")
    template_type: str | None = Field(
        default=None, description="Template type (coding, debug, review, etc.)"
    )


class PromptGeneratorTool(BaseTool):
    """Tool for generating and managing AI prompts."""

    name = "prompt_generator"
    description = "Generate, save, and load AI prompts for various tasks."
    args_model = PromptGeneratorArgs

    _TEMPLATES: dict[str, str] = {
        "coding": (
            "You are an expert software engineer. Write clean, efficient, and "
            "well-documented code. Follow best practices for the language/framework. "
            "Include error handling and type hints where appropriate."
        ),
        "debug": (
            "You are a senior debugging expert. Analyze the provided code or error "
            "message systematically. Identify the root cause and provide a targeted "
            "fix. Explain your reasoning step by step."
        ),
        "review": (
            "You are a meticulous code reviewer. Analyze the code for correctness, "
            "security, performance, and maintainability. Provide specific, actionable "
            "feedback with line references."
        ),
        "architect": (
            "You are a solutions architect. Design scalable, maintainable systems. "
            "Consider trade-offs, patterns, and best practices. Provide diagrams "
            "or pseudocode where helpful."
        ),
        "devops": (
            "You are a DevOps engineer. Optimize deployment, CI/CD, and infrastructure. "
            "Consider security, scalability, and cost. Provide automation scripts."
        ),
        "research": (
            "You are a technical researcher. Gather comprehensive information, "
            "compare options, and provide well-supported recommendations. "
            "Include pros, cons, and alternatives."
        ),
        "explain": (
            "You are a technical educator. Explain complex concepts clearly and "
            "concisely. Use examples and analogies. Build understanding progressively."
        ),
    }

    def __init__(self) -> None:
        super().__init__()
        self._prompt_dir = Path.home() / ".sago" / "prompts"
        self._prompt_dir.mkdir(parents=True, exist_ok=True)

    def _run(
        self,
        operation: str,
        name: str | None = None,
        content: str | None = None,
        template_type: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Perform a prompt operation.

        Args:
            operation: Operation type.
            name: Prompt name.
            content: Prompt content.
            template_type: Template type.

        Returns:
            Operation result.
        """
        if operation == "generate":
            return self._generate_prompt(template_type, content)
        elif operation == "list":
            return self._list_prompts()
        elif operation == "save":
            if name is None or content is None:
                return "Error: name and content required for save"
            return self._save_prompt(name, content)
        elif operation == "load":
            if name is None:
                return "Error: name required for load"
            return self._load_prompt(name)
        elif operation == "template":
            return self._get_template(template_type)

        return f"Error: Unknown operation: {operation}"

    def _generate_prompt(self, template_type: str | None, custom_content: str | None) -> str:
        """Generate a prompt from template or custom content."""
        if custom_content:
            from sago.engine.prompt_enhancer import enhance_prompt

            res = enhance_prompt(custom_content, agent_role=template_type or "Specialist")
            if res.was_modified:
                return (
                    f"Generated Enhanced Prompt:\n\n"
                    f"Intent: {res.intent_summary}\n\n"
                    f"{res.enhanced_prompt}"
                )
            return f"Generated prompt:\n\n{custom_content}"

        if template_type and template_type in self._TEMPLATES:
            return f"Template ({template_type}):\n\n{self._TEMPLATES[template_type]}"

        if template_type:
            return f"Unknown template type: {template_type}. Available: {', '.join(self._TEMPLATES.keys())}"

        return f"Available templates: {', '.join(self._TEMPLATES.keys())}"

    def _list_prompts(self) -> str:
        """List saved prompts."""
        prompts = list(self._prompt_dir.glob("*.txt"))
        if not prompts:
            return "No saved prompts"

        lines = ["Saved prompts:"]
        for p in sorted(prompts):
            lines.append(f"  {p.stem}")
        return "\n".join(lines)

    def _save_prompt(self, name: str, content: str) -> str:
        """Save a prompt to disk."""
        path = self._prompt_dir / f"{name}.txt"
        path.write_text(content, encoding="utf-8")
        return f"Saved prompt '{name}' to {path}"

    def _load_prompt(self, name: str) -> str:
        """Load a prompt from disk."""
        path = self._prompt_dir / f"{name}.txt"
        if not path.exists():
            return f"Prompt '{name}' not found"
        return path.read_text(encoding="utf-8")

    def _get_template(self, template_type: str | None) -> str:
        """Get a prompt template."""
        if template_type is None:
            return "Available templates:\n" + "\n".join(
                f"  {k}: {v[:50]}..." for k, v in self._TEMPLATES.items()
            )

        if template_type in self._TEMPLATES:
            return f"Template ({template_type}):\n\n{self._TEMPLATES[template_type]}"

        return f"Unknown template: {template_type}"
