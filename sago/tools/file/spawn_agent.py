"""Spawn Agent Tool - Delegate tasks to specialist agents."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class SpawnAgentArgs(BaseModel):
    """Arguments for SpawnAgentTool."""

    task: str = Field(description="Task to delegate to the agent")
    agent_name: str = Field(description="Name of the agent (e.g. python-engineer, debugger, devops)")
    context: str = Field(default="", description="Optional context from previous work")


class SpawnAgentTool(BaseTool):
    """Tool for spawning specialist agents to handle tasks."""

    name = "spawn_agent"
    description = (
        "Delegate a task to a specialist agent. Available agents: "
        "python-engineer, javascript-engineer, java-engineer, go-engineer, "
        "rust-engineer, cpp-engineer, ruby-engineer, php-engineer, "
        "frontend-engineer, backend-engineer, fullstack-engineer, "
        "mobile-engineer, ios-engineer, android-engineer, flutter-engineer, "
        "data-engineer, ml-engineer, data-analyst, "
        "devops, sre-engineer, kubernetes-engineer, docker-engineer, "
        "security-engineer, appsec-engineer, "
        "qa-engineer, test-engineer, automation-engineer, "
        "code-reviewer, debugger, software-engineer, "
        "technical-writer, documentation-updater, "
        "database-engineer, api-engineer, "
        "performance-engineer, cloud-engineer, "
        "ui-engineer, ux-engineer, css-engineer, "
        "system-architect, solution-architect"
    )
    args_model = SpawnAgentArgs

    def _run(
        self,
        task: str,
        agent_name: str,
        context: str = "",
        **kwargs: Any,
    ) -> str:
        """Spawn an agent to handle a task."""
        import os
        from pathlib import Path

        api_key = os.environ.get("OPENROUTER_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
        if not api_key:
            return "Error: No API key set. Set OPENROUTER_API_KEY or OPENAI_API_KEY."

        # Get agent profile for system prompt
        system_prompt = self._get_agent_prompt(agent_name, context)

        # Use simple_executor to run the task
        from sago.engine.simple_executor import execute_agent_task

        result = execute_agent_task(
            task=task,
            agent_role=agent_name.replace("-", " ").title(),
            system_prompt=system_prompt,
            api_key=api_key,
            model="openrouter/free",
            max_tokens=4096,
            max_iterations=5,
        )

        output = result.get("output", "No response")
        tools_used = result.get("tool_calls", [])

        response_parts = [f"[Agent: {agent_name}]"]
        if tools_used:
            response_parts.append(f"Tools used: {', '.join(t['tool'] for t in tools_used)}")
        response_parts.append(output)

        return "\n".join(response_parts)

    def _get_agent_prompt(self, agent_name: str, context: str = "") -> str:
        """Get system prompt for an agent."""
        try:
            from sago.agents.registry import get_agent
            definition = get_agent(agent_name)
            if definition:
                prompt = definition.system_prompt
                if context:
                    prompt += f"\n\n## Context\n{context}"
                return prompt
        except Exception:
            pass

        # Fallback prompts for common agents
        prompts = {
            "python-engineer": "You are a Python expert. Write clean, efficient Python code. Use type hints, docstrings, and follow PEP 8.",
            "javascript-engineer": "You are a JavaScript/TypeScript expert. Write modern ES6+ code with proper error handling.",
            "java-engineer": "You are a Java expert. Write clean OOP Java code with proper design patterns.",
            "go-engineer": "You are a Go expert. Write idiomatic Go with proper error handling and concurrency.",
            "rust-engineer": "You are a Rust expert. Write safe, efficient Rust code with proper ownership.",
            "frontend-engineer": "You are a frontend expert. Build responsive, accessible UIs with modern frameworks.",
            "backend-engineer": "You are a backend expert. Build scalable APIs and services.",
            "fullstack-engineer": "You are a full-stack expert. Build complete web applications.",
            "devops": "You are a DevOps expert. Manage infrastructure, CI/CD, containers, and deployment.",
            "security-engineer": "You are a security expert. Identify vulnerabilities and implement security best practices.",
            "qa-engineer": "You are a QA expert. Write comprehensive tests and ensure code quality.",
            "debugger": "You are a debugging expert. Find and fix bugs systematically.",
            "code-reviewer": "You are a code review expert. Review code for quality, security, and best practices.",
            "data-engineer": "You are a data engineering expert. Build data pipelines and ETL processes.",
            "ml-engineer": "You are an ML engineer. Build and deploy machine learning models.",
            "database-engineer": "You are a database expert. Design schemas, optimize queries, and manage data.",
            "technical-writer": "You are a technical writing expert. Write clear documentation and guides.",
            "system-architect": "You are a systems architect. Design scalable, maintainable system architectures.",
        }

        base_prompt = prompts.get(agent_name, f"You are a {agent_name} specialist.")
        if context:
            base_prompt += f"\n\n## Context\n{context}"

        return base_prompt
