"""Sago Production Engine

Main orchestration engine that ties together:
- Streaming responses
- Session management
- Dynamic task delegation
- Effort/thinking levels
- Multi-agent coordination
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sago.orchestrator.delegator import TaskDelegator, TaskPlan
from sago.sessions.manager import (
    Session,
    SessionManager,
    Thread,
    ThreadStatus,
)
from sago.streaming.handler import (
    EffortLevel,
    StreamingResponse,
    StreamPrinter,
)


@dataclass
class EngineConfig:
    """Configuration for the production engine."""

    max_workers: int = 4
    default_effort: str = "medium"
    show_thinking: bool = False
    use_streaming: bool = True
    auto_delegate: bool = True
    timeout: float = 300.0


class ProductionEngine:
    """Main production engine for Sago."""

    def __init__(self, config: EngineConfig | None = None) -> None:
        self.config = config or EngineConfig()
        self.session_manager = SessionManager(max_workers=self.config.max_workers)
        self.delegator = TaskDelegator()
        self.stream_printer = StreamPrinter(show_thinking=self.config.show_thinking)
        self._last_cleanup = time.time()
        self._session_ttl = 3600  # 1 hour TTL for sessions

        # Event callbacks
        self._on_task_start: list[Callable[..., None]] = []
        self._on_task_complete: list[Callable[..., None]] = []
        self._on_error: list[Callable[..., None]] = []

    def _cleanup_sessions(self) -> None:
        """Clean up old sessions to prevent unbounded growth."""
        now = time.time()
        if now - self._last_cleanup < 300:  # Cleanup every 5 minutes
            return
        self._last_cleanup = now

        try:
            sessions = self.session_manager.list_sessions()
            for session_data in sessions:
                session_id = session_data.get("id", "")
                updated_at = session_data.get("updated_at", 0)
                if now - updated_at > self._session_ttl:
                    self.session_manager.delete_session(session_id)
        except Exception:
            pass

    def on_task_start(self, callback: Callable[..., None]) -> None:
        """Register callback for task start."""
        self._on_task_start.append(callback)

    def on_task_complete(self, callback: Callable[..., None]) -> None:
        """Register callback for task completion."""
        self._on_task_complete.append(callback)

    def on_error(self, callback: Callable[..., None]) -> None:
        """Register callback for errors."""
        self._on_error.append(callback)

    def create_session(self, title: str = "New Session") -> Session:
        """Create a new session."""
        return self.session_manager.create_session(title)

    def run_task(
        self,
        task: str,
        agent: str | None = None,
        effort: str | None = None,
        session_id: str | None = None,
        stream: bool = True,
    ) -> dict[str, Any]:
        """Run a task with full orchestration.

        Args:
            task: The task to execute
            agent: Specific agent to use (None for auto-delegation)
            effort: Effort level (minimal/low/medium/high/max)
            session_id: Session to attach to (creates new if None)
            stream: Whether to stream output

        Returns:
            Result dictionary with content, stats, and metadata
        """
        # Create or get session
        self._cleanup_sessions()
        if session_id:
            session = self.session_manager.get_session(session_id)
            if not session:
                session = self.session_manager.create_session(task[:50])
        else:
            session = self.session_manager.create_session(task[:50])

        # Determine effort level
        effort_level = EffortLevel(effort or self.config.default_effort)

        # Create streaming response
        response = StreamingResponse(
            effort=effort_level,
            show_thinking=self.config.show_thinking,
        )

        if stream:
            response.add_callback(self.stream_printer)

        response.start()

        try:
            # Analyze and plan
            response.add_thinking("Analyzing task requirements...")
            plan = self.delegator.analyze_task(task)

            # Use specified agent or auto-delegate
            agent_name = agent or plan.primary_agent

            response.add_thinking(
                f"Selected agent: {agent_name}",
                confidence=0.9,
            )

            # Create thread
            thread = self.session_manager.create_thread(
                session.id,
                agent_name,
                task,
                effort=effort_level.value,
            )

            if not thread:
                raise RuntimeError("Failed to create thread")

            # Notify callbacks
            for cb in self._on_task_start:
                cb({"task": task, "agent": agent_name, "thread_id": thread.id})

            # Execute the task
            response.add_thinking(f"Executing with {effort_level.value} effort...")

            # Get the agent and execute
            from sago.agents.registry import get_agent

            agent_def = get_agent(agent_name)

            if not agent_def:
                # Fallback: try to find any available agent
                from sago.agents.registry import list_agents

                available = list_agents()
                if available:
                    fallback_name = available[0].get("name", "")
                    if fallback_name:
                        agent_def = get_agent(fallback_name)
                        if agent_def:
                            agent_name = agent_name
                            response.add_thinking(f"Fallback to agent: {agent_name}")

            if agent_def:
                response.add_thinking(f"Using agent: {agent_def.codename}")

                # Build context
                context = self._build_context(task, plan, session)

                # Execute with the agent
                result = self._execute_agent(
                    agent_def,
                    task,
                    context,
                    response,
                    effort_level,
                )
            else:
                result = f"Agent not found: {agent_name}"

            # Complete the response
            response.end()

            # Update thread
            thread.result = result
            thread.status = ThreadStatus.COMPLETED
            thread.completed_at = time.time()

            # Add message to session
            session.add_message("user", task)
            session.add_message("assistant", result, agent_name)

            # Notify callbacks
            for cb in self._on_task_complete:
                cb(
                    {
                        "task": task,
                        "agent": agent_name,
                        "result": result[:500],
                        "stats": response.get_stats(),
                    }
                )

            return {
                "success": True,
                "content": result,
                "stats": response.get_stats(),
                "thinking": response.get_thinking_traces(),
                "session_id": session.id,
                "thread_id": thread.id,
                "agent": agent_name,
                "plan": plan.to_dict(),
            }

        except Exception as e:
            response.add_error(str(e))
            response.end()

            for cb in self._on_error:
                cb({"task": task, "error": str(e)})

            return {
                "success": False,
                "error": str(e),
                "stats": response.get_stats(),
                "session_id": session.id,
            }

    def run_chain(
        self,
        task: str,
        agent_chain: list[str],
        effort: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Run a task through an agent chain.

        Each agent processes the output of the previous one.
        """
        session = (
            self.session_manager.get_session(session_id)
            if session_id
            else self.session_manager.create_session(task[:50])
        )

        current_input = task
        results = []
        effort_level = EffortLevel(effort or self.config.default_effort)

        for i, agent_name in enumerate(agent_chain):
            print(f"\n{'=' * 60}")
            print(f"Step {i + 1}/{len(agent_chain)}: {agent_name}")
            print(f"{'=' * 60}\n")

            result = self.run_task(
                current_input,
                agent=agent_name,
                effort=effort_level.value,
                session_id=session.id,
            )

            results.append(result)

            if not result.get("success"):
                return {
                    "success": False,
                    "error": f"Chain failed at step {i + 1} ({agent_name}): {result.get('error')}",
                    "results": results,
                    "session_id": session.id,
                }

            current_input = result.get("content", "")

        return {
            "success": True,
            "content": current_input,
            "chain_results": results,
            "session_id": session.id,
        }

    def run_parallel(
        self,
        tasks: list[dict[str, str]],
        effort: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Run multiple tasks in parallel.

        Args:
            tasks: List of {"task": "...", "agent": "..."} dicts
            effort: Effort level for all tasks
            session_id: Session to attach to

        Returns:
            Combined results from all parallel tasks
        """
        session = (
            self.session_manager.get_session(session_id)
            if session_id
            else self.session_manager.create_session("Parallel Tasks")
        )

        # Create threads for all tasks
        threads = []
        for task_info in tasks:
            thread = self.session_manager.create_thread(
                session.id,
                task_info.get("agent", "developer"),
                task_info["task"],
                effort=effort or self.config.default_effort,
            )
            if thread:
                threads.append((thread, task_info))

        # Execute all threads in parallel
        futures = []
        for thread, task_info in threads:
            future = self.session_manager.execute_thread(
                thread.id,
                lambda t: self._execute_thread_task(t, task_info["task"]),
            )
            if future:
                futures.append((thread, future))

        # Wait for all to complete
        results = []
        for thread, future in futures:
            try:
                result = future.result(timeout=self.config.timeout)
                results.append(
                    {
                        "thread_id": thread.id,
                        "success": True,
                        "content": result,
                    }
                )
            except Exception as e:
                results.append(
                    {
                        "thread_id": thread.id,
                        "success": False,
                        "error": str(e),
                    }
                )

        return {
            "success": all(r.get("success") for r in results),
            "results": results,
            "session_id": session.id,
        }

    def _execute_agent(
        self,
        agent_def: Any,
        task: str,
        context: str,
        response: StreamingResponse,
        effort: EffortLevel,
    ) -> str:
        """Execute a task with an agent."""
        # Build the prompt
        system_prompt = agent_def.system_prompt
        full_prompt = f"{system_prompt}\n\n## Task\n{task}\n\n## Context\n{context}"

        # Get LLM provider
        from sago.config.loader import get_config
        from sago.llm.factory import get_provider

        config = get_config()
        default_provider = config.llm_providers.default
        provider_config = config.llm_providers.providers.get(default_provider)
        if provider_config:
            provider = get_provider(
                default_provider,
                {
                    "api_key_env": provider_config.api_key_env,
                    "base_url": provider_config.base_url,
                    "model": provider_config.model,
                    "max_tokens": provider_config.max_tokens,
                    "temperature": provider_config.temperature,
                },
            )
        else:
            provider = None

        if provider:
            response.add_thinking("Generating response...")
            result = provider.generate(full_prompt)
            response.add_text(result)
            return result

        # Fallback to agent's built-in execution
        return f"[Agent {agent_def.name}] Processing: {task[:200]}"

    def _build_context(
        self,
        task: str,
        plan: TaskPlan,
        session: Session,
    ) -> str:
        """Build context for agent execution."""
        context_parts = [
            f"Task Type: {plan.task_type.value}",
            f"Complexity: {plan.complexity.value}",
            f"Effort Level: {plan.effort}",
            f"Reasoning: {plan.reasoning}",
        ]

        # Add recent messages
        if session.messages:
            recent = session.messages[-5:]
            context_parts.append("\nRecent conversation:")
            for msg in recent:
                context_parts.append(f"  {msg.role}: {msg.content[:200]}")

        return "\n".join(context_parts)

    def _execute_thread_task(self, thread: Thread, task: str) -> str:
        """Execute a task for a thread."""
        from sago.agents.registry import get_agent

        agent_def = get_agent(thread.agent_name)

        if agent_def:
            return self._execute_agent(
                agent_def,
                task,
                "",
                StreamingResponse(effort=EffortLevel(thread.effort)),
                EffortLevel(thread.effort),
            )
        return f"Agent not found: {thread.agent_name}"

    def get_session(self, session_id: str) -> Session | None:
        """Get a session by ID."""
        return self.session_manager.get_session(session_id)

    def list_sessions(self) -> list[dict[str, Any]]:
        """List all sessions."""
        return self.session_manager.list_sessions()

    def shutdown(self) -> None:
        """Shutdown the engine."""
        self.session_manager.shutdown()
