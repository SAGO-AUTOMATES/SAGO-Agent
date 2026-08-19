"""Agent Spawner - Creates and manages agent instances with structured handoffs.

Handles agent creation, context passing, feedback loops, and multi-agent orchestration
with recursion protection and cycle detection.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from sago.agents.handoff import HandoffContext, get_recursion_guard
from sago.agents.registry import get_agent
from sago.config.loader import SagoConfig, get_config
from sago.database import MessageStore, Session

logger = logging.getLogger("sago.spawner")


class AgentSpawner:
    """Spawns and manages specialist agents.

    Handles:
    - Creating CrewAI agents from definitions
    - Multi-agent handoffs with structured context
    - Feedback loops between agents
    - Session persistence
    - Tool resolution
    - Recursion protection
    """

    def __init__(self, config: SagoConfig | None = None) -> None:
        self.config = config or get_config()
        self._crew_agents: dict[str, Any] = {}
        self._tools: dict[str, Any] = {}
        self._tool_classes: dict[str, type] = {}

    def spawn(
        self,
        agent_name: str,
        session: Session | None = None,
        context: HandoffContext | dict[str, Any] | None = None,
        provider: str | None = None,
        model_override: str | None = None,
    ) -> Any | None:
        """Spawn a specialist agent as a CrewAI Agent.

        Args:
            agent_name: Name of the agent to spawn.
            session: Optional session for persistence.
            context: HandoffContext or dict with context from previous agents.
            provider: Optional LLM provider override.
            model_override: Optional model override.

        Returns:
            CrewAI Agent instance or None if not found.
        """
        from crewai import Agent

        definition = get_agent(agent_name)
        if definition is None:
            logger.error(f"Agent not found: {agent_name}")
            return None

        # Resolve tools via crewai_wrappers
        tools = self._resolve_tools(definition.tools)

        # Build system prompt with structured context
        system_prompt = definition.system_prompt
        if isinstance(context, HandoffContext):
            context_str = context.get_context_for(agent_name)
            system_prompt += f"\n\n{context_str}"
        elif context:
            context_str = "\n\n".join(f"## {k}\n{v}" for k, v in context.items())
            system_prompt += f"\n\n## Context from Previous Agent\n{context_str}"

        # Create CrewAI agent
        agent = Agent(
            role=definition.role,
            goal=definition.description,
            backstory=system_prompt,
            tools=tools,
            verbose=self.config.settings.verbose_output,
            allow_delegation=len(definition.handoff_to) > 0,
            max_iter=definition.max_iterations,
            llm=self._get_llm(model_override or definition.model_preference, provider),
        )

        self._crew_agents[agent_name] = agent
        logger.info(f"Spawned agent: {agent_name} ({definition.codename})")
        return agent

    def execute_with_agent(
        self,
        agent_name: str,
        task: str,
        session_id: str | None = None,
        parent_context: HandoffContext | dict[str, Any] | None = None,
        provider: str | None = None,
        model_override: str | None = None,
    ) -> str:
        """Execute a task using a specific agent.

        Args:
            agent_name: Agent to use.
            task: Task description.
            session_id: Optional session ID for persistence.
            parent_context: HandoffContext or dict with context from parent agent.
            provider: Optional LLM provider override.
            model_override: Optional model override.

        Returns:
            Task result.
        """
        from crewai import Crew, Task

        # Create or get session
        if session_id:
            session = Session(session_id)
        else:
            session = Session()
            session.create(title=task[:100])

        # Spawn the agent
        agent = self.spawn(
            agent_name,
            session=session,
            context=parent_context,
            provider=provider,
            model_override=model_override,
        )
        if agent is None:
            return f"Error: Could not spawn agent '{agent_name}'"

        # Create task
        crew_task = Task(
            description=task,
            agent=agent,
            expected_output="A comprehensive response addressing the task completely.",
        )

        # Execute
        crew = Crew(
            agents=[agent],
            tasks=[crew_task],
            verbose=self.config.settings.verbose_output,
        )

        result = crew.kickoff()

        # Store result
        msg_store = MessageStore(session.id)
        msg_store.add(
            role="assistant",
            content=str(result),
            agent_name=agent_name,
        )

        return str(result)

    def orchestrate(
        self,
        task: str,
        session_id: str | None = None,
        agent_chain: list[str] | None = None,
        max_handoffs: int = 5,
        enable_feedback: bool = True,
    ) -> str:
        """Orchestrate a task through multiple agents with handoffs and feedback loops.

        This is the multi-agent loop that:
        1. Spawns the initial agent
        2. Executes the task
        3. If the agent hands off, spawns the next agent with structured context
        4. Supports feedback loops (agent B can request clarification from agent A)
        5. Breaks chain on errors instead of propagating error strings
        6. Detects cycles and prevents infinite recursion

        Args:
            task: Task description.
            session_id: Optional session ID.
            agent_chain: Optional predefined chain of agents.
            max_handoffs: Maximum number of agent handoffs.
            enable_feedback: Whether to enable feedback loops.

        Returns:
            Final result.
        """
        # Create session
        session = Session(session_id)
        if not session_id:
            session.create(title=task[:100], agent_chain=agent_chain or [])

        # Initialize structured context
        handoff_ctx = HandoffContext(
            original_task=task,
            depth=0,
            parent_chain=[],
        )

        # Get recursion guard for this thread
        guard = get_recursion_guard()
        guard.reset()

        # Use predefined chain or auto-route
        if agent_chain:
            chain = agent_chain
        else:
            chain = self._plan_chain(task)

        result = ""
        for i, agent_name in enumerate(chain[: max_handoffs + 1]):
            logger.info(f"Agent {i + 1}/{len(chain)}: {agent_name}")

            # Check recursion guard
            allowed, reason = guard.can_spawn(agent_name)
            if not allowed:
                logger.warning(f"Recursion guard blocked {agent_name}: {reason}")
                handoff_ctx.errors.append(f"Blocked: {reason}")
                break

            guard.enter(agent_name)

            try:
                # Build step task with structured context
                if i == 0:
                    step_task = task
                else:
                    # Provide rich context for subsequent agents
                    step_task = self._build_step_task(task, handoff_ctx, agent_name)

                # Execute
                step_result = self.execute_with_agent(
                    agent_name=agent_name,
                    task=step_task,
                    session_id=session.id,
                    parent_context=handoff_ctx,
                )

                # Check for errors — break chain on failure
                if step_result.startswith("Error:"):
                    logger.error(f"Agent {agent_name} failed: {step_result}")
                    handoff_ctx.add_result(agent_name, step_result, success=False)
                    # Break chain on error — don't propagate error strings
                    result = step_result
                    break

                # Record successful result
                handoff_ctx.add_result(agent_name, step_result, success=True)
                result = step_result

                # Feedback loop: if agent requested feedback, handle it
                if enable_feedback and handoff_ctx.feedback_requests:
                    result = self._handle_feedback_loop(handoff_ctx, agent_name, result, session.id)

            finally:
                guard.exit(agent_name)

        return result

    def _build_step_task(self, original_task: str, ctx: HandoffContext, next_agent: str) -> str:
        """Build a rich task prompt for the next agent in the chain."""
        from sago.engine.prompt_enhancer import enhance_prompt

        enhancement = enhance_prompt(
            task=original_task,
            agent_role=next_agent,
            extra_context=f"Chained execution step for {next_agent}",
        )

        parts = []

        # Enhanced goal and original request
        parts.append(f"## Target Objective\n{enhancement.intent_summary}")
        parts.append(f"## Original User Request\n{original_task}")

        # What previous agents did
        if ctx.completed_agents:
            parts.append("## What Has Been Done")
            for prev_agent in ctx.completed_agents:
                if prev_agent in ctx.agent_results:
                    result_preview = ctx.agent_results[prev_agent][:500]
                    parts.append(f"### {prev_agent}\n{result_preview}")

        # Files created
        if ctx.files_created:
            parts.append(
                "## Files Created/Modified\n" + "\n".join(f"- {f}" for f in ctx.files_created)
            )

        # Errors to be aware of
        if ctx.errors:
            parts.append("## Known Issues\n" + "\n".join(f"- {e}" for e in ctx.errors[-3:]))

        # Acceptance criteria
        if enhancement.acceptance_criteria:
            crit_lines = "\n".join(f"- {c}" for c in enhancement.acceptance_criteria)
            parts.append(f"## Acceptance Criteria\n{crit_lines}")

        # What this agent should focus on
        parts.append(
            f"## Your Task as {next_agent}\n"
            f"Continue the work above. You are the specialist {next_agent}. "
            f"Review what has been completed, address open criteria, and provide your specialist contribution."
        )

        return "\n\n".join(parts)

    def _handle_feedback_loop(
        self,
        ctx: HandoffContext,
        current_agent: str,
        current_result: str,
        session_id: str,
    ) -> str:
        """Handle feedback requests between agents.

        If agent B needs clarification from agent A, this method:
        1. Finds the pending feedback request
        2. Re-engages agent A with the question
        3. Passes the answer back to agent B
        """
        pending = [
            r
            for r in ctx.feedback_requests
            if r.to_agent in ctx.completed_agents and not r.answered
        ]

        if not pending:
            return current_result

        for request in pending:
            # Ask the previous agent for clarification
            feedback_task = (
                f"The {request.from_agent} has a question for you:\n\n"
                f"{request.question}\n\n"
                f"Provide a concise, specific answer."
            )

            try:
                answer = self.execute_with_agent(
                    agent_name=request.to_agent,
                    task=feedback_task,
                    session_id=session_id,
                    parent_context=ctx,
                )
                request.respond(answer)

                # Inject the answer into the current agent's context
                current_result += (
                    f"\n\n## Feedback from {request.to_agent}\nQ: {request.question}\nA: {answer}"
                )
            except Exception as e:
                logger.warning(f"Feedback loop failed: {e}")
                current_result += (
                    f"\n\n## Feedback Failed\nCould not get feedback from {request.to_agent}: {e}"
                )

        return current_result

    def orchestrate_parallel(
        self,
        subtasks: list[dict[str, str]],
        session_id: str | None = None,
        max_workers: int = 4,
    ) -> list[dict[str, Any]]:
        """Execute multiple subtasks in parallel using threads.

        Args:
            subtasks: List of dicts with 'agent' and 'task' keys.
            session_id: Optional session ID.
            max_workers: Maximum parallel workers.

        Returns:
            List of results with 'agent', 'task', 'result' keys.
        """
        import concurrent.futures

        from sago.engine.simple_executor import execute_agent_task

        session = Session(session_id)
        if not session_id:
            session.create(title="Parallel execution")

        # Shared context for all parallel agents
        shared_ctx = HandoffContext(
            original_task=subtasks[0].get("task", "") if subtasks else "",
            task_type="parallel",
        )

        results: list[dict[str, Any]] = []

        def execute_subtask(subtask: dict[str, str]) -> dict[str, Any]:
            agent_name = subtask.get("agent", "sago-orchestrator")
            task = subtask.get("task", "")
            try:
                # Build context for this subtask
                ctx_str = shared_ctx.get_context_for(agent_name)

                result = execute_agent_task(
                    task=task,
                    agent_role=agent_name.replace("-", " ").title(),
                    system_prompt=self._get_parallel_prompt(agent_name, ctx_str),
                    model=self.config.llm.model,
                    api_key=os.environ.get(
                        "OPENROUTER_API_KEY", os.environ.get("OPENAI_API_KEY", "")
                    ),
                )
                return {
                    "agent": agent_name,
                    "task": task,
                    "result": result.get("output", ""),
                    "success": result.get("success", False),
                    "tool_calls": result.get("tool_calls", []),
                    "files_created": result.get("files_created", []),
                }
            except Exception as e:
                return {
                    "agent": agent_name,
                    "task": task,
                    "result": f"Error: {e}",
                    "success": False,
                }

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(execute_subtask, st): st for st in subtasks[:max_workers]}
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())

        return results

    def _get_parallel_prompt(self, agent_name: str, context: str) -> str:
        """Get a prompt for parallel agent execution."""
        base = self._get_agent_prompt_for_name(agent_name)
        return (
            f"{base}\n\n"
            f"You are running in parallel with other agents. "
            f"Focus on your specific task. Be self-contained.\n\n"
            f"{context}"
        )

    def _get_agent_prompt_for_name(self, agent_name: str) -> str:
        """Get the base prompt for an agent by name."""
        try:
            definition = get_agent(agent_name)
            if definition:
                return definition.system_prompt
        except Exception as e:
            logger.debug("Failed to get agent definition for %s: %s", agent_name, e)
        return f"You are a {agent_name.replace('-', ' ')} specialist."

    def _plan_chain(self, task: str) -> list[str]:
        """Plan an agent chain based on the task.

        Uses the smart router for intelligent agent selection from 300+ profiles.
        """
        # Use smart router for intelligent selection
        try:
            from sago.agents.router import route_for_chain

            chain = route_for_chain(task, max_agents=4)
            if chain:
                return chain
        except Exception as e:
            logger.debug("Smart router failed for chain planning, using fallback: %s", e)

        # Fallback to basic keyword matching
        task_lower = task.lower()
        chain: list[str] = []

        keyword_map: dict[str, list[str]] = {
            "python-engineer": ["python", "fastapi", "django", "flask", "pydantic", "pip"],
            "backend-engineer": ["web", "backend", "api", "fullstack", "server", "fastapi"],
            "frontend-engineer": [
                "ui",
                "ux",
                "css",
                "layout",
                "component",
                "responsive",
                "react",
                "vue",
                "frontend",
            ],
            "rust-engineer": ["rust", "systems", "performance", "memory", "concurrent", "cargo"],
            "go-engineer": ["go", "golang", "microservice", "grpc"],
            "architect": [
                "architecture",
                "design",
                "scale",
                "pattern",
                "structure",
                "plan",
                "system",
            ],
            "data-architect": ["database", "schema", "data", "sql", "model", "er diagram"],
            "devops": ["deploy", "docker", "kubernetes", "ci/cd", "pipeline", "container", "sre"],
            "cloud-architect": ["aws", "gcp", "azure", "cloud", "serverless", "lambda"],
            "reviewer": ["review", "quality", "check", "audit", "best practice", "lint"],
            "security-engineer": [
                "security",
                "vulnerability",
                "injection",
                "xss",
                "csrf",
                "auth",
                "threat model",
                "owasp",
            ],
            "database-administrator": [
                "optimize",
                "slow query",
                "index",
                "performance",
                "explain",
                "db",
            ],
            "api-engineer": ["api design", "rest", "graphql", "openapi", "swagger", "endpoint"],
            "ml-engineer": ["machine learning", "ml", "model", "train", "neural", "ai", "llm"],
            "documentation-updater": [
                "documentation",
                "docs",
                "readme",
                "guide",
                "tutorial",
                "write",
            ],
            "tester": ["test", "pytest", "unit test", "integration", "coverage", "assert"],
        }

        scores: dict[str, int] = {}
        for agent_name, keywords in keyword_map.items():
            score = sum(1 for kw in keywords if kw in task_lower)
            if score > 0:
                scores[agent_name] = score

        if scores:
            sorted_agents = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            chain = [name for name, _ in sorted_agents[:3]]
        else:
            chain = ["python-engineer", "reviewer"]

        if chain and chain[0] in ("reviewer", "security-engineer", "database-administrator"):
            if len(chain) > 1:
                chain = [chain[1], chain[0]]
            else:
                chain = ["python-engineer"] + chain

        return chain

    def _resolve_tools(self, tool_names: list[str]) -> list[Any]:
        """Convert tool names to CrewAI tool instances."""
        from sago.tools.crewai_wrappers import get_crewai_tool

        resolved = []
        for name in tool_names:
            crewai_tool = get_crewai_tool(name)
            if crewai_tool:
                resolved.append(crewai_tool)
            else:
                logger.warning(f"No CrewAI wrapper for tool: {name}")
        return resolved

    def _get_llm(
        self, model_override: str | None = None, provider_override: str | None = None
    ) -> Any:
        """Get a CrewAI LLM for the configured provider."""
        import os

        from crewai import LLM

        provider_name = provider_override or self.config.llm_providers.default
        provider_config = self.config.llm_providers.providers.get(provider_name)

        if provider_config is None:
            return None

        # Get API key from environment
        api_key_env = provider_config.api_key_env or f"{provider_name.upper()}_API_KEY"
        api_key = os.environ.get(api_key_env, "")

        # For OpenRouter, also check OPENAI_API_KEY as fallback
        if not api_key and provider_name == "openrouter":
            api_key = os.environ.get("OPENAI_API_KEY", "")

        if not api_key:
            logger.warning(f"No API key found for {provider_name} (env: {api_key_env})")
            return None

        model = model_override or provider_config.model
        base_url = provider_config.base_url

        # For OpenRouter, use OPENAI_API_KEY and base_url
        if provider_name == "openrouter" and not base_url:
            base_url = "https://openrouter.ai/api/v1"
            if not api_key:
                api_key = os.environ.get("OPENAI_API_KEY", "")

        try:
            llm = LLM(
                model=model,
                api_key=api_key,
                base_url=base_url,
                temperature=provider_config.temperature,
                max_tokens=min(provider_config.max_tokens, 4096),
            )
            return llm
        except Exception as e:
            logger.warning(f"Could not create LLM: {e}")
            return None
