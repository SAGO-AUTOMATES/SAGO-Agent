"""Spawn Agent Tool - Delegate tasks to specialist agents with recursion protection."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool

logger = logging.getLogger("sago.tools.spawn_agent")


class SpawnAgentArgs(BaseModel):
    """Arguments for SpawnAgentTool."""

    task: str = Field(default="", description="Task to delegate to the agent")
    agent_name: str = Field(
        default="",
        description="Name of the agent (e.g. python-engineer, java-engineer, go-engineer, devops-engineer)",
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

    def _resolve_target_agent(self, agent_name: str, task: str) -> str:
        """Resolve agent name using smart routing."""
        candidate = (agent_name or "").strip().lower().replace("_", "-")
        if not candidate:
            t_lower = task.lower()
            if "python" in t_lower or ".py" in t_lower:
                candidate = "python-engineer"
            elif "java" in t_lower and "script" not in t_lower:
                candidate = "java-engineer"
            elif (
                "golang" in t_lower
                or "go " in t_lower
                or "go/" in t_lower
                or ".go" in t_lower
                or " go " in f" {t_lower} "
            ):
                candidate = "go-engineer"
            elif "rust" in t_lower or ".rs" in t_lower:
                candidate = "rust-engineer"
            elif "c++" in t_lower or "cpp" in t_lower:
                candidate = "cpp-engineer"
            elif "frontend" in t_lower or "react" in t_lower or "vue" in t_lower:
                candidate = "frontend-engineer"
            elif (
                "devops" in t_lower or "docker" in t_lower or "k8s" in t_lower or "ci/cd" in t_lower
            ):
                candidate = "devops-engineer"
            elif "test" in t_lower or "qa" in t_lower or "pytest" in t_lower:
                candidate = "qa-engineer"
            elif "security" in t_lower or "audit" in t_lower:
                candidate = "security-engineer"
            else:
                try:
                    from sago.agents.router import route_single

                    resolved = route_single(task)
                    if resolved and resolved != "software-engineer":
                        candidate = resolved
                    else:
                        candidate = "software-engineer"
                except Exception:
                    candidate = "software-engineer"

        try:
            from sago.agents.registry import AGENT_ALIASES, AGENTS

            if candidate in AGENTS:
                return candidate
            if candidate in AGENT_ALIASES:
                return AGENT_ALIASES[candidate]
            if f"{candidate}-engineer" in AGENTS:
                return f"{candidate}-engineer"
        except Exception as e:
            logger.debug("Failed to resolve agent name from registry: %s", e)

        return candidate or "software-engineer"

    def _run(
        self,
        task: str = "",
        agent_name: str = "",
        context: str = "",
        feedback: str = "",
        guard: Any = None,
        **kwargs: Any,
    ) -> str:
        """Spawn an agent to handle a task with recursion protection.

        Args:
            guard: Optional shared RecursionGuard. Callers orchestrating across
                multiple worker threads (e.g. parallel chain steps) must pass
                their guard explicitly — thread-local lookup would otherwise
                give each worker a fresh guard and disable cycle/depth checks.
        """
        actual_task = (
            task
            or kwargs.get("prompt")
            or kwargs.get("instruction")
            or kwargs.get("query")
            or kwargs.get("description")
            or ""
        )
        raw_agent = (
            agent_name
            or kwargs.get("agent")
            or kwargs.get("role")
            or kwargs.get("agent_role")
            or kwargs.get("name")
            or kwargs.get("target")
            or ""
        )

        # --- Argument validation: reject empty/trivial tasks ---
        if not actual_task.strip() or len(actual_task.strip()) < 10:
            logger.warning(
                "Rejected trivial task (%d chars): '%s'",
                len(actual_task.strip()),
                actual_task.strip()[:100],
            )
            return (
                "REJECTED: spawn_agent requires a meaningful task description (min 10 characters).\n"
                f"Got: '{actual_task.strip()}'\n\n"
                "Fix: Provide a specific task. Examples:\n"
                '  - "Create a Python calculator with add, subtract, multiply, divide functions"\n'
                '  - "Write unit tests for the authentication module"\n'
                '  - "Review the API endpoints for security vulnerabilities"'
            )

        resolved_agent = self._resolve_target_agent(raw_agent, actual_task)
        logger.debug(
            "Resolved agent '%s' -> '%s' (raw: '%s')", raw_agent, resolved_agent, agent_name
        )

        # --- Simple analyze spawn gate: tiny codebase (≤5 files) → no sub-agent ---
        try:
            import re as _re
            from pathlib import Path as _Path

            if "analyz" in actual_task.lower():
                _fc: int | None = None
                _skip = {
                    ".git",
                    ".sago",
                    "__pycache__",
                    ".ruff_cache",
                    ".pytest_cache",
                    ".mypy_cache",
                    ".venv",
                    "venv",
                    "node_modules",
                    "env",
                }
                _skip_sfx = {".pyc", ".pyo", ".bak", ".orig"}
                for _m in _re.finditer(r"(?:\"|')?(/[\w\-/\.]+)(?:\"|')?", actual_task):
                    _p = _Path(_m.group(1).rstrip(".,;:"))
                    if _p.exists() and _p.is_dir():
                        _c = 0
                        for _sub in _p.rglob("*"):
                            if not _sub.is_file():
                                continue
                            if any(part in _skip for part in _sub.parts):
                                continue
                            if any(
                                part.startswith(".") and part not in (".", "..")
                                for part in _sub.parts
                            ):
                                if _sub.name.startswith("."):
                                    continue
                            if _sub.suffix.lower() in _skip_sfx:
                                continue
                            if _sub.suffix.lower() == ".md":
                                continue
                            if _sub.name in ("package-lock.json", "package.json"):
                                continue
                            _c += 1
                            if _c > 50:
                                break
                        _fc = _c
                        break
                if _fc is not None and _fc <= 5:
                    logger.info("spawn_agent blocked for simple analyze tiny codebase (fc=%d)", _fc)
                    return (
                        f"REJECTED: spawn_agent disabled for simple analyze with {_fc} files (≤5). "
                        f"Use direct tools: glob_files (pattern='**/*', path='<dir>') + code_analyzer on each file. "
                        f"Not spawning sub-agent '{resolved_agent}'. "
                        f"Budget: max 15 tools, 8 iterations, 8k tokens — analyze directly."
                    )
        except Exception as _e:
            logger.debug("spawn gate check failed: %s", _e)

        # Warn if agent resolution was purely heuristic (no explicit agent_name given)
        if not raw_agent.strip():
            task_lower = actual_task.lower()
            domain_keywords = [
                "python",
                "java",
                "go ",
                "golang",
                "rust",
                "c++",
                "cpp",
                "frontend",
                "backend",
                "fullstack",
                "devops",
                "docker",
                "k8s",
                "security",
                "test",
                "qa",
                "database",
                "api",
                "mobile",
                "android",
                "ios",
                "react",
                "vue",
                "angular",
            ]
            if not any(kw in task_lower for kw in domain_keywords):
                return (
                    f"REJECTED: Could not determine a specialist agent for this task.\n"
                    f"Task: '{actual_task[:200]}'\n"
                    f"Resolved to: '{resolved_agent}' (generic fallback)\n\n"
                    "Fix: Explicitly set agent_name to a specialist.\n"
                    "Examples: python-engineer, java-engineer, go-engineer, devops-engineer"
                )

        # Use the explicitly shared guard when provided (multi-threaded chains),
        # otherwise fall back to the thread-local guard.
        if guard is None:
            from sago.agents.handoff import get_recursion_guard

            guard = get_recursion_guard()
        allowed, reason = guard.can_spawn(resolved_agent)
        if not allowed:
            logger.warning("Recursion guard blocked agent '%s': %s", resolved_agent, reason)
            return (
                f"Cannot spawn agent '{resolved_agent}': {reason}\n\n"
                f"Please complete this task directly without delegating further."
            )

        from sago.llm.tui_providers import resolve_active_llm_config

        llm_cfg = resolve_active_llm_config()
        api_key = llm_cfg["api_key"]
        if not api_key:
            from sago.llm.registry import ProviderSpec, fallback_order, get_provider_spec

            key_names: list[str] = []
            for name in fallback_order():
                spec: ProviderSpec | None = get_provider_spec(name)
                if spec and spec.api_key_env:
                    key_names.append(spec.api_key_env)
            return f"Error: No API key set. Set one of: {', '.join(key_names)}."

        # Record dev trace event for agent delegation
        try:
            from sago.tracking.dev_tracer import TraceEventType, get_dev_tracer

            get_dev_tracer().record(
                event_type=TraceEventType.AGENT_ROUTING,
                source="spawn_agent",
                action=f"DELEGATE -> {resolved_agent}",
                data={
                    "target_agent": resolved_agent,
                    "task": actual_task[:200],
                    "depth": guard.depth + 1,
                },
            )
        except Exception as e:
            logger.debug("Failed to record dev trace event: %s", e)
        guard.enter(resolved_agent)
        logger.info(
            "Spawning agent '%s' (depth %d/%d)", resolved_agent, guard.depth + 1, guard.max_depth
        )

        try:
            return self._execute_agent(
                agent_name=resolved_agent,
                task=actual_task,
                context=context,
                feedback=feedback,
                api_key=api_key,
                guard=guard,
                llm_cfg=llm_cfg,
            )
        finally:
            guard.exit(resolved_agent)

    # Fallback agent chains: if primary fails, try these alternatives
    _FALLBACK_AGENTS: dict[str, list[str]] = {
        "python-engineer": ["software-engineer", "fullstack-developer"],
        "java-engineer": ["software-engineer", "fullstack-developer"],
        "go-engineer": ["software-engineer", "rust-engineer"],
        "rust-engineer": ["software-engineer", "cpp-engineer"],
        "cpp-engineer": ["software-engineer"],
        "frontend-engineer": ["fullstack-developer", "ui-engineer"],
        "backend-engineer": ["fullstack-developer", "api-engineer"],
        "fullstack-developer": ["software-engineer"],
        "devops-engineer": ["cloud-engineer", "sre-engineer"],
        "mobile-engineer": ["android-engineer", "ios-engineer"],
        "qa-engineer": ["test-engineer", "automation-engineer"],
        "security-engineer": ["appsec-engineer"],
        "data-engineer": ["database-engineer", "ml-engineer"],
    }

    def _execute_agent(
        self,
        agent_name: str,
        task: str,
        context: str,
        feedback: str,
        api_key: str,
        guard: Any,
        llm_cfg: dict[str, Any] | None = None,
    ) -> str:
        """Execute the agent with proper prompts and context. Retries with fallback agents on failure."""
        # Use active model from settings/env/config
        if llm_cfg is None:
            from sago.llm.tui_providers import resolve_active_llm_config

            llm_cfg = resolve_active_llm_config()

        model = llm_cfg["model"]
        base_url = llm_cfg["base_url"]

        # Inherit callbacks from parent context (processor → spawned agent)
        from sago.engine.simple_executor import get_execution_callbacks

        inherited = get_execution_callbacks()

        # Build fallback chain: primary agent + fallbacks
        fallbacks = self._FALLBACK_AGENTS.get(agent_name, ["software-engineer"])
        agents_to_try = [agent_name] + [a for a in fallbacks if a != agent_name]
        logger.debug("Agent fallback chain: %s", agents_to_try)

        last_error = None
        for try_agent in agents_to_try:
            system_prompt = self._build_system_prompt(try_agent, task, context, feedback, guard)

            # Try with user-selected model first, fallback to free model if distinct
            models_to_try = [model]
            if model != "openrouter/free":
                models_to_try.append("openrouter/free")

            for try_model in models_to_try:
                try:
                    import uuid

                    from sago.engine.simple_executor import execute_agent_task

                    spawn_session_id = f"spawn-{try_agent}-{uuid.uuid4().hex[:8]}"

                    # Enable YOLO mode for spawned agent (auto-approve all tools)
                    try:
                        from sago.permissions import get_permission_manager

                        get_permission_manager().set_yolo_mode(spawn_session_id, True)
                    except Exception:
                        pass  # Non-critical if permission manager unavailable

                    result = execute_agent_task(
                        task=task,
                        agent_role=try_agent.replace("-", " ").title(),
                        system_prompt=system_prompt,
                        api_key=api_key,
                        model=try_model,
                        base_url=base_url,
                        max_tokens=8192,
                        max_iterations=20,
                        wall_timeout=300.0,
                        session_id=spawn_session_id,
                        on_tool_call=inherited["on_tool_call"],
                        on_tool_result=inherited["on_tool_result"],
                        on_thinking=inherited["on_thinking"],
                    )

                    output = result.get("output", "")
                    tools_used = result.get("tool_calls", [])
                    files_created = result.get("files_created", [])

                    # Quality gate: reject empty/trivial responses
                    if not output or len(output.strip()) < 20:
                        last_error = f"Agent '{try_agent}' produced empty/trivial output ({len(output or '')} chars)"
                        continue

                    # Quality gate: reject responses that are mostly failure indicators
                    failure_signals = [
                        "i cannot",
                        "i'm unable",
                        "i don't have",
                        "error:",
                        "failed to",
                    ]
                    failure_count = sum(1 for s in failure_signals if s in output.lower())
                    if failure_count >= 2 and len(output.strip()) < 200:
                        last_error = (
                            f"Agent '{try_agent}' produced failure-heavy output: {output[:100]}"
                        )
                        continue

                    # Success — format and return
                    used_different_agent = try_agent != agent_name
                    response = self._format_response(
                        try_agent, output, tools_used, files_created, guard
                    )
                    logger.info(
                        "Agent '%s' completed successfully (model=%s, tools=%d, files=%d)",
                        try_agent,
                        try_model,
                        len(tools_used),
                        len(files_created),
                    )
                    if used_different_agent:
                        response = (
                            f"[Note: '{agent_name}' was unavailable, "
                            f"used '{try_agent}' instead]\n\n" + response
                        )
                    return response

                except Exception as e:
                    last_error = f"{try_agent}/{try_model}: {e}"
                    logger.debug("Agent '%s' with model '%s' failed: %s", try_agent, try_model, e)
                    continue

        # All agents and models failed
        logger.error(
            "All %d agent(s) failed for task '%s'. Last error: %s",
            len(agents_to_try),
            task[:100],
            last_error,
        )
        return (
            f"Agent '{agent_name}' could not be spawned after trying {len(agents_to_try)} agent(s).\n"
            f"Last error: {last_error}\n\n"
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

        # Add context from previous agents — handle both raw strings and HandoffContext
        context_section = ""
        if context:
            # Check if context is a HandoffContext object (from structured handoff)
            from sago.agents.handoff import HandoffContext

            if isinstance(context, HandoffContext):
                context_section = (
                    f"\n\n## Handoff Context\n{context.get_compact_handoff_prompt(agent_name)}"
                )
            else:
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
        except Exception as e:
            logger.debug("Failed to load agent prompt from registry: %s", e)

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

        # Parse and include handoff notes if present
        handoff_notes = self._extract_handoff_notes(output)
        if handoff_notes:
            response_parts.append(f"\n[Handoff Notes]: {handoff_notes}")

        return "\n".join(response_parts)

    @staticmethod
    def _extract_handoff_notes(output: str) -> str:
        """Extract Handoff Notes section from agent output."""
        import re

        match = re.search(
            r"##?\s*Handoff\s*Notes?\s*\n(.*?)(?=\n##?\s|\Z)",
            output,
            re.DOTALL | re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()
        return ""
