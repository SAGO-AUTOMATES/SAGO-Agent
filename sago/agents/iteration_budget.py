"""Iteration and Token Budget Controller for Main and Subagents.

Provides thread-safe iteration tracking with strict limits to prevent runaway
subagent execution loops while allowing refunding for non-LLM operations.
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger("sago.agents.iteration_budget")


class IterationBudget:
    """Thread-safe iteration budget tracker."""

    def __init__(
        self,
        max_iterations: int = 50,
        name: str = "agent",
    ) -> None:
        self.name = name
        self._max = max_iterations
        self._remaining = max_iterations
        self._consumed = 0
        self._lock = threading.Lock()

    def consume(self, amount: int = 1) -> bool:
        """Consume iteration steps. Returns True if within budget, False if exhausted."""
        with self._lock:
            if self._remaining < amount:
                logger.warning(
                    "Iteration budget exhausted for %s (consumed: %d, max: %d)",
                    self.name,
                    self._consumed,
                    self._max,
                )
                return False
            self._remaining -= amount
            self._consumed += amount
            return True

    def refund(self, amount: int = 1) -> None:
        """Refund iteration steps (e.g. for non-LLM or synthetic turns)."""
        with self._lock:
            self._remaining = min(self._max, self._remaining + amount)
            self._consumed = max(0, self._consumed - amount)

    @property
    def remaining(self) -> int:
        with self._lock:
            return self._remaining

    @property
    def consumed(self) -> int:
        with self._lock:
            return self._consumed

    @property
    def is_exhausted(self) -> bool:
        with self._lock:
            return self._remaining <= 0

    def reset(self) -> None:
        """Reset budget back to initial limit."""
        with self._lock:
            self._remaining = self._max
            self._consumed = 0
