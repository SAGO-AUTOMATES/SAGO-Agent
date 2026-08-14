"""Handoff Context - Structured context passing between agents with recursion protection."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("sago.handoff")

# Thread-local storage for recursion tracking
_thread_local = threading.local()

# Global limits
MAX_AGENT_DEPTH = 5
MAX_SAME_AGENT_VISITS = 2
MAX_TOTAL_VISITS = 15


@dataclass
class HandoffContext:
    """Structured context passed between agents during handoffs.

    Replaces raw string concatenation with typed, queryable context.
    """

    original_task: str
    task_type: str = "general"
    completed_agents: list[str] = field(default_factory=list)
    agent_results: dict[str, str] = field(default_factory=dict)
    agent_feedback: dict[str, list[str]] = field(default_factory=dict)
    files_created: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    depth: int = 0
    parent_chain: list[str] = field(default_factory=list)
    shared_state: dict[str, Any] = field(default_factory=dict)
    feedback_requests: list[FeedbackRequest] = field(default_factory=list)

    def add_result(self, agent_name: str, result: str, success: bool = True) -> None:
        """Record an agent's result."""
        self.agent_results[agent_name] = result
        self.completed_agents.append(agent_name)
        if not success:
            self.errors.append(f"{agent_name}: {result[:500]}")

    def request_feedback(self, from_agent: str, to_agent: str, question: str) -> FeedbackRequest:
        """Request feedback from another agent."""
        req = FeedbackRequest(
            from_agent=from_agent,
            to_agent=to_agent,
            question=question,
        )
        self.feedback_requests.append(req)
        return req

    def get_context_for(self, agent_name: str) -> str:
        """Build a context string optimized for a specific agent."""
        parts = []

        # Original task
        parts.append(f"## Original Task\n{self.original_task}")

        # Completed work (exclude the requesting agent itself)
        if self.completed_agents:
            agents_done = [a for a in self.completed_agents if a != agent_name]
            if agents_done:
                parts.append(f"## Previously Completed By: {', '.join(agents_done)}")

        # Relevant results (last 2 agents' output for context window)
        for prev_agent in self.completed_agents[-2:]:
            if prev_agent in self.agent_results:
                result = self.agent_results[prev_agent]
                parts.append(f"## Previous Result ({prev_agent})\n{result[:2000]}")

        # Files created so far
        if self.files_created:
            parts.append("## Files Created\n" + "\n".join(f"- {f}" for f in self.files_created))

        # Errors to be aware of
        if self.errors:
            parts.append("## Known Issues\n" + "\n".join(f"- {e}" for e in self.errors[-3:]))

        # Pending feedback requests
        pending = [r for r in self.feedback_requests if r.to_agent == agent_name and not r.answered]
        if pending:
            for req in pending:
                parts.append(f"## Feedback Request from {req.from_agent}\n{req.question}")

        # Depth warning
        if self.depth > 2:
            parts.append(
                f"## Warning\nThis is depth {self.depth} of {MAX_AGENT_DEPTH}. "
                f"Provide your best final answer. Do not spawn more agents."
            )

        return "\n\n".join(parts)

    def to_state_delta(self) -> dict[str, Any]:
        """Generate a zero-redundancy state delta object for lightweight agent handoffs."""
        return {
            "task_intent": self.original_task[:500],
            "task_type": self.task_type,
            "chain": list(self.completed_agents),
            "files_touched": list(self.files_created),
            "recent_errors": list(self.errors[-2:]),
            "depth": self.depth,
            "shared_keys": list(self.shared_state.keys()),
        }

    def get_compact_handoff_prompt(self, agent_name: str) -> str:
        """Generate a token-minimized handoff prompt saving ~70% context overhead."""
        lines = [f"[AGENT HANDOFF DELTA -> {agent_name.upper()}]"]
        lines.append(f"Task: {self.original_task}")
        if self.completed_agents:
            lines.append(f"Completed Prior Stages: {', '.join(self.completed_agents)}")
        if self.files_created:
            lines.append(f"Active Files: {', '.join(self.files_created)}")
        if self.errors:
            lines.append(f"Unresolved Issues: {'; '.join(self.errors[-2:])}")

        # Last agent result summarized
        if self.completed_agents:
            last_agent = self.completed_agents[-1]
            last_res = self.agent_results.get(last_agent, "")
            if last_res:
                lines.append(f"Output from {last_agent}:\n{last_res[:800]}")

        lines.append(
            f"\nFocus: Execute your specialized domain role for {agent_name} and output your verified solution."
        )
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage/transport."""
        return {
            "original_task": self.original_task,
            "task_type": self.task_type,
            "completed_agents": self.completed_agents,
            "files_created": self.files_created,
            "errors": self.errors,
            "depth": self.depth,
            "parent_chain": self.parent_chain,
            "state_delta": self.to_state_delta(),
        }


@dataclass
class FeedbackRequest:
    """A request for feedback between agents."""

    from_agent: str
    to_agent: str
    question: str
    answer: str = ""
    answered: bool = False

    def respond(self, answer: str) -> None:
        """Provide an answer to this feedback request."""
        self.answer = answer
        self.answered = True


class RecursionGuard:
    """Prevents infinite recursion in agent spawning.

    Tracks:
    - Current depth (how many agents deep we are)
    - Visited agents (which agents have been called)
    - Total visit count (prevents runaway chains)
    """

    def __init__(
        self,
        max_depth: int = MAX_AGENT_DEPTH,
        max_same_visits: int = MAX_SAME_AGENT_VISITS,
        max_total: int = MAX_TOTAL_VISITS,
    ) -> None:
        self.max_depth = max_depth
        self.max_same_visits = max_same_visits
        self.max_total = max_total
        self._visits: dict[str, int] = {}
        self._total_visits = 0
        self._parent_chain: list[str] = []
        self._lock = threading.Lock()

    @property
    def depth(self) -> int:
        return len(self._parent_chain)

    @property
    def parent_chain(self) -> list[str]:
        return list(self._parent_chain)

    def can_spawn(self, agent_name: str) -> tuple[bool, str]:
        """Check if we can spawn this agent.

        Returns:
            (allowed, reason) tuple.
        """
        with self._lock:
            # Check depth
            if self.depth >= self.max_depth:
                return False, (
                    f"Max depth {self.max_depth} reached "
                    f"(chain: {' -> '.join(self._parent_chain + [agent_name])}). "
                    f"Cannot spawn {agent_name}."
                )

            # Check total visits
            if self._total_visits >= self.max_total:
                return False, (
                    f"Max total visits ({self.max_total}) reached. Cannot spawn more agents."
                )

            # Check same-agent visits
            visits = self._visits.get(agent_name, 0)
            if visits >= self.max_same_visits:
                return False, (
                    f"Agent '{agent_name}' has been visited {visits} times. "
                    f"Max allowed: {self.max_same_visits}. "
                    f"Possible cycle detected: {' -> '.join(self._parent_chain + [agent_name])}"
                )

            # Check for direct cycle (A -> B -> A)
            if agent_name in self._parent_chain:
                cycle_start = self._parent_chain.index(agent_name)
                cycle = self._parent_chain[cycle_start:] + [agent_name]
                return False, (
                    f"Cycle detected: {' -> '.join(cycle)}. "
                    f"Agent '{agent_name}' is already in the chain."
                )

            return True, "OK"

    def enter(self, agent_name: str) -> None:
        """Record entering an agent."""
        with self._lock:
            self._parent_chain.append(agent_name)
            self._visits[agent_name] = self._visits.get(agent_name, 0) + 1
            self._total_visits += 1
            logger.debug(
                f"Guard enter: {agent_name} (depth={self.depth}, "
                f"visits={self._visits[agent_name]}, total={self._total_visits})"
            )

    def exit(self, agent_name: str) -> None:
        """Record exiting an agent."""
        with self._lock:
            if self._parent_chain and self._parent_chain[-1] == agent_name:
                self._parent_chain.pop()
            logger.debug(f"Guard exit: {agent_name} (depth={self.depth})")

    def get_handoff_prompt_addendum(self) -> str:
        """Get a prompt addendum that instructs the agent about recursion limits."""
        remaining = self.max_depth - self.depth
        if remaining <= 1:
            return (
                "\n\n## IMPORTANT: Recursion Limit Approaching\n"
                f"You are at depth {self.depth}/{self.max_depth}. "
                "You MUST complete this task yourself without spawning more agents. "
                "Provide your final answer directly."
            )
        return (
            f"\n\n## Recursion Depth\n"
            f"Current depth: {self.depth}/{self.max_depth}. "
            f"Remaining spawns allowed: {remaining - 1}."
        )

    def reset(self) -> None:
        """Reset the guard for a new top-level task."""
        with self._lock:
            self._visits.clear()
            self._total_visits = 0
            self._parent_chain.clear()


# Global recursion guard per thread
_thread_guards: dict[int, RecursionGuard] = {}


def get_recursion_guard() -> RecursionGuard:
    """Get or create a recursion guard for the current thread."""
    tid = threading.get_ident()
    if tid not in _thread_guards:
        _thread_guards[tid] = RecursionGuard()
    return _thread_guards[tid]


def reset_recursion_guard() -> None:
    """Reset the recursion guard for the current thread."""
    tid = threading.get_ident()
    if tid in _thread_guards:
        _thread_guards[tid].reset()
    else:
        _thread_guards[tid] = RecursionGuard()
