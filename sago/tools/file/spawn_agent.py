"""Spawn Agent Tool - Delegate tasks to specialist agents with recursion protection."""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class SpawnAgentArgs(BaseModel):
    """Arguments for SpawnAgentTool."""

    task: str = Field(description="Task to delegate to the agent")
    agent_name: str = Field(
        description="Name of the agent (e.g. python-engineer, debugger, devops)"
    )
    context: str = Field(default="", description="Optional context from previous work")
    feedback: str = Field(
        default="",
        description="Feedback or clarification to include for the agent",
    )


class SpawnAgentTool(BaseTool):
    """Tool for spawning specialist agents to handle tasks.

    Includes recursion protection, cycle detection, and structured prompts
    to ensure sub-agents provide proper output back to the orchestrator.
    """

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
        feedback: str = "",
        **kwargs: Any,
    ) -> str:
        """Spawn an agent to handle a task with recursion protection."""
        from sago.agents.handoff import get_recursion_guard

        # Check recursion guard before spawning
        guard = get_recursion_guard()
        allowed, reason = guard.can_spawn(agent_name)
        if not allowed:
            return (
                f"Cannot spawn agent '{agent_name}': {reason}\n\n"
                f"Please complete this task directly without delegating further."
            )

        api_key = os.environ.get("OPENROUTER_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
        if not api_key:
            return "Error: No API key set. Set OPENROUTER_API_KEY or OPENAI_API_KEY."

        # Register this agent in the guard
        guard.enter(agent_name)

        try:
            return self._execute_agent(
                agent_name=agent_name,
                task=task,
                context=context,
                feedback=feedback,
                api_key=api_key,
                guard=guard,
            )
        finally:
            guard.exit(agent_name)

    def _execute_agent(
        self,
        agent_name: str,
        task: str,
        context: str,
        feedback: str,
        api_key: str,
        guard: Any,
    ) -> str:
        """Execute the agent with proper prompts and context."""
        # Build the system prompt with full context
        system_prompt = self._build_system_prompt(agent_name, task, context, feedback, guard)

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
                    max_tokens=8192,
                    max_iterations=20,
                )

                output = result.get("output", "No response")
                tools_used = result.get("tool_calls", [])
                files_created = result.get("files_created", [])

                # Check if we got a real response
                if output and not output.startswith("Error:") and len(output.strip()) > 10:
                    return self._format_response(
                        agent_name, output, tools_used, files_created, guard
                    )

                last_error = output or "Empty response"

            except Exception as e:
                last_error = str(e)
                continue

        # All models failed
        return (
            f"Agent '{agent_name}' could not be spawned.\n"
            f"Reason: {last_error}\n\n"
            f"Alternatives:\n"
            f"  1. Try running the task directly (without agent delegation)\n"
            f"  2. Check your API key and credits at https://openrouter.ai/settings/credits\n"
            f"  3. Use /agent <name> to switch to a specialist agent first"
        )

    def _build_system_prompt(
        self,
        agent_name: str,
        task: str,
        context: str,
        feedback: str,
        guard: Any,
    ) -> str:
        """Build a comprehensive system prompt with context and output instructions."""
        # Get base agent prompt from registry
        base_prompt = self._get_agent_prompt(agent_name)

        # Add structured output instructions
        output_instructions = self._get_output_instructions(agent_name)

        # Add context from previous agents
        context_section = ""
        if context:
            context_section = f"\n\n## Context From Parent Agent\n{context}"

        # Add feedback if provided
        feedback_section = ""
        if feedback:
            feedback_section = f"\n\n## Feedback / Clarification\n{feedback}"

        # Add recursion depth info
        depth_addendum = guard.get_handoff_prompt_addendum()

        # Compose final prompt
        prompt = f"""{base_prompt}

{output_instructions}
{context_section}
{feedback_section}
{depth_addendum}

## Your Task
{task}

## CRITICAL: Response Format
You MUST structure your response as follows:

1. **Analysis**: Briefly analyze what was asked and what you found/did
2. **Work Done**: List specific changes, files created/modified, code written
3. **Results**: Show key outputs, test results, or verification
4. **Issues Found**: Any problems, blockers, or concerns (if none, say "None")
5. **Recommendations**: Next steps or suggestions for the orchestrator
6. **Handoff Notes**: What the next agent should know or focus on

Be specific. Include file paths, function names, and concrete details.
Do NOT just say "I completed the task" — show evidence of your work.
"""
        return prompt

    def _get_output_instructions(self, agent_name: str) -> str:
        """Get agent-specific output format instructions."""
        instructions = {
            "python-engineer": (
                "Output format: Show file paths created/modified, key functions implemented, "
                "and any test results. Include code snippets for critical sections."
            ),
            "code-reviewer": (
                "Output format: List issues found by severity (critical/major/minor), "
                "reference specific line numbers, and provide fix suggestions."
            ),
            "debugger": (
                "Output format: State root cause, show the exact bug location, "
                "and provide the fix with before/after code comparison."
            ),
            "devops-engineer": (
                "Output format: List infrastructure changes, deployment steps, "
                "and any configuration modifications with file paths."
            ),
            "security-engineer": (
                "Output format: List vulnerabilities by CVSS score range, "
                "affected files/functions, and remediation steps."
            ),
            "architect": (
                "Output format: Show architecture decisions, component relationships, "
                "and any diagrams (ASCII) or structural descriptions."
            ),
        }
        return instructions.get(
            agent_name,
            "Be specific about what you did, what files you touched, and what the results were.",
        )

    def _get_agent_prompt(self, agent_name: str) -> str:
        """Get system prompt for an agent."""
        try:
            from sago.agents.registry import get_agent

            definition = get_agent(agent_name)
            if definition:
                return definition.system_prompt
        except Exception:
            pass

        # Fallback prompts for common agents
        prompts = {
            "python-engineer": "You are a senior Python engineer. Write clean, efficient, well-documented Python code with type hints and proper error handling.",
            "java-engineer": "You are a senior Java engineer. Write clean OOP Java code with proper design patterns, SOLID principles, and comprehensive error handling.",
            "go-engineer": "You are a senior Go engineer. Write idiomatic Go with proper error handling, concurrency patterns, and clear package structure.",
            "rust-engineer": "You are a senior Rust engineer. Write safe, efficient Rust code with proper ownership, borrowing, and error handling.",
            "cpp-engineer": "You are a senior C++ engineer. Write modern C++ with RAII, smart pointers, and proper memory management.",
            "frontend-engineer": "You are a senior frontend engineer. Build responsive, accessible, performant UIs with modern frameworks.",
            "backend-engineer": "You are a senior backend engineer. Build scalable, secure APIs and services with proper architecture.",
            "fullstack-developer": "You are a senior full-stack developer. Build complete, production-ready web applications.",
            "devops-engineer": "You are a senior DevOps engineer. Manage infrastructure, CI/CD, containers, and deployment pipelines.",
            "security-engineer": "You are a senior security engineer. Identify vulnerabilities, implement security best practices, and ensure compliance.",
            "qa-engineer": "You are a senior QA engineer. Write comprehensive tests, identify edge cases, and ensure code quality.",
            "reviewer": "You are a senior code reviewer. Review code for quality, security, performance, and best practices.",
            "data-engineer": "You are a senior data engineer. Build robust data pipelines and ETL processes.",
            "ml-engineer": "You are a senior ML engineer. Build and deploy machine learning models with proper validation.",
            "database-engineer": "You are a senior database engineer. Design efficient schemas, optimize queries, and ensure data integrity.",
            "technical-writer": "You are a senior technical writer. Write clear, accurate, comprehensive documentation.",
            "architect": "You are a senior systems architect. Design scalable, maintainable, well-documented system architectures.",
            "kubernetes-engineer": "You are a senior Kubernetes engineer. Manage k8s clusters, deployments, services, and networking.",
            "docker-engineer": "You are a senior Docker engineer. Build optimized containers and docker-compose configurations.",
            "cloud-engineer": "You are a senior cloud engineer. Design and manage cloud infrastructure with best practices.",
            "performance-engineer": "You are a senior performance engineer. Identify bottlenecks, optimize code, and measure improvements.",
        }
        return prompts.get(
            agent_name, f"You are a senior {agent_name.replace('-', ' ')} specialist."
        )

    def _format_response(
        self,
        agent_name: str,
        output: str,
        tools_used: list[dict],
        files_created: list[str],
        guard: Any,
    ) -> str:
        """Format the agent response with structured metadata."""
        response_parts = [f"[Agent: {agent_name}]"]

        if tools_used:
            tool_names = [t.get("tool", "unknown") for t in tools_used]
            response_parts.append(f"Tools used: {', '.join(tool_names)}")

        if files_created:
            response_parts.append(f"Files created/modified: {', '.join(files_created)}")

        # Add depth info
        response_parts.append(f"Depth: {guard.depth}/{guard.max_depth}")

        response_parts.append(output)
        return "\n".join(response_parts)
