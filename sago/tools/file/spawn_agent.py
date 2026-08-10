"""Spawn Agent Tool - Delegate tasks to specialist agents."""

from __future__ import annotations

import os
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
        "Delegate a task to a specialist agent. Use the exact agent name. "
        "Common agents: python-engineer, java-engineer, go-engineer, rust-engineer, cpp-engineer, "
        "ruby-engineer, php-engineer, dart-engineer, swift-engineer, kotlin-engineer, "
        "frontend-engineer, backend-engineer, fullstack-developer, mobile-engineer, "
        "android-engineer, ios-engineer, data-engineer, ml-engineer, ai-engineer, "
        "devops-engineer, sre-engineer, kubernetes-engineer, docker-engineer, cloud-engineer, "
        "aws-engineer, azure-engineer, gcp-engineer, "
        "security-engineer, appsec-engineer, penetration-engineer, "
        "qa-engineer, test-engineer, automation-engineer, "
        "reviewer, architect, cloud-architect, data-architect, "
        "technical-writer, database-engineer, api-engineer, "
        "performance-engineer, caching-engineer, network-engineer, "
        "blockchain-engineer, crypto-engineer, iot-engineer, "
        "game-developer, unity-developer, unreal-developer, "
        "rust-engineer, golang-engineer, haskell-engineer, "
        "lua-engineer, perl-engineer, r-engineer, scala-engineer"
    )
    args_model = SpawnAgentArgs
    risk_level = "high"

    def _run(
        self,
        task: str,
        agent_name: str,
        context: str = "",
        **kwargs: Any,
    ) -> str:
        """Spawn an agent to handle a task."""
        api_key = os.environ.get("OPENROUTER_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
        if not api_key:
            return "Error: No API key set. Set OPENROUTER_API_KEY or OPENAI_API_KEY."

        # Get agent profile for system prompt
        system_prompt = self._get_agent_prompt(agent_name, context)

        # Use configured model from config, not hardcoded
        try:
            from sago.config.loader import get_config
            config = get_config()
            model = config.llm.model or "openrouter/free"
        except Exception:
            model = "openrouter/free"

        # Try with configured model first, fallback to free model
        models_to_try = [model]
        if model != "openrouter/free":
            models_to_try.append("openrouter/free")

        last_error = None
        for try_model in models_to_try:
            try:
                from sago.engine.simple_executor import execute_agent_task

                result = execute_agent_task(
                    task=task,
                    agent_role=agent_name.replace("-", " ").title(),
                    system_prompt=system_prompt,
                    api_key=api_key,
                    model=try_model,
                    max_tokens=4096,
                    max_iterations=5,
                )

                output = result.get("output", "No response")
                tools_used = result.get("tool_calls", [])

                # Check if we got a real response (not just an error)
                if output and not output.startswith("Error:") and len(output.strip()) > 10:
                    response_parts = [f"[Agent: {agent_name}]"]
                    if tools_used:
                        response_parts.append(f"Tools used: {', '.join(t['tool'] for t in tools_used)}")
                    response_parts.append(output)
                    return "\n".join(response_parts)

                last_error = output or "Empty response"

            except Exception as e:
                last_error = str(e)
                continue

        # All models failed — provide helpful error with alternatives
        return (
            f"Agent '{agent_name}' could not be spawned.\n"
            f"Reason: {last_error}\n\n"
            f"Alternatives:\n"
            f"  1. Try running the task directly (without agent delegation)\n"
            f"  2. Check your API key and credits at https://openrouter.ai/settings/credits\n"
            f"  3. Use /agent <name> to switch to a specialist agent first"
        )

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
            "java-engineer": "You are a Java expert. Write clean OOP Java code with proper design patterns.",
            "go-engineer": "You are a Go expert. Write idiomatic Go with proper error handling and concurrency.",
            "rust-engineer": "You are a Rust expert. Write safe, efficient Rust code with proper ownership.",
            "cpp-engineer": "You are a C++ expert. Write modern C++ with RAII and smart pointers.",
            "frontend-engineer": "You are a frontend expert. Build responsive, accessible UIs with modern frameworks.",
            "backend-engineer": "You are a backend expert. Build scalable APIs and services.",
            "fullstack-developer": "You are a full-stack expert. Build complete web applications.",
            "devops-engineer": "You are a DevOps expert. Manage infrastructure, CI/CD, containers, and deployment.",
            "security-engineer": "You are a security expert. Identify vulnerabilities and implement security best practices.",
            "qa-engineer": "You are a QA expert. Write comprehensive tests and ensure code quality.",
            "reviewer": "You are a code review expert. Review code for quality, security, and best practices.",
            "data-engineer": "You are a data engineering expert. Build data pipelines and ETL processes.",
            "ml-engineer": "You are an ML engineer. Build and deploy machine learning models.",
            "database-engineer": "You are a database expert. Design schemas, optimize queries, and manage data.",
            "technical-writer": "You are a technical writing expert. Write clear documentation and guides.",
            "architect": "You are a systems architect. Design scalable, maintainable system architectures.",
            "kubernetes-engineer": "You are a Kubernetes expert. Manage k8s clusters, deployments, services.",
            "docker-engineer": "You are a Docker expert. Build and optimize containers and docker-compose.",
            "cloud-engineer": "You are a cloud expert. Design and manage cloud infrastructure.",
        }

        base_prompt = prompts.get(agent_name, f"You are a {agent_name} specialist.")
        if context:
            base_prompt += f"\n\n## Context\n{context}"

        return base_prompt
