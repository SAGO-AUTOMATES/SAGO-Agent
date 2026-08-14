"""Input Summarization and Compaction

Handles long inputs by summarizing before processing to save tokens.
Provides session compaction for maintaining context in long conversations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CompactedContext:
    """Compacted context from a long conversation."""

    summary: str
    key_points: list[str]
    decisions: list[str]
    action_items: list[str]
    entities: list[str]
    original_length: int
    compacted_length: int

    @property
    def compression_ratio(self) -> float:
        if self.original_length == 0:
            return 0.0
        return 1.0 - (self.compacted_length / self.original_length)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "key_points": self.key_points,
            "decisions": self.decisions,
            "action_items": self.action_items,
            "entities": self.entities,
            "original_length": self.original_length,
            "compacted_length": self.compacted_length,
            "compression_ratio": round(self.compression_ratio * 100, 1),
        }


class InputSummarizer:
    """Summarizes long inputs to save tokens."""

    # Thresholds
    WORD_THRESHOLD = 500  # Words before summarization
    TOKEN_ESTIMATE_RATIO = 4  # Characters per token

    # Patterns for extraction
    ERROR_PATTERN = re.compile(
        r"(?:error|exception|traceback|failed|failure)[^\n]*",
        re.IGNORECASE,
    )
    STACK_TRACE_PATTERN = re.compile(
        r'(?:at\s+\w[\w.]*\(|File\s+".*",\s*line\s+\d+)',
        re.MULTILINE,
    )
    CODE_BLOCK_PATTERN = re.compile(
        r"```[\s\S]*?```",
        re.MULTILINE,
    )
    URL_PATTERN = re.compile(
        r"https?://\S+",
    )

    def should_summarize(self, text: str) -> bool:
        """Check if text should be summarized."""
        word_count = len(text.split())
        return word_count > self.WORD_THRESHOLD

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count."""
        return len(text) // self.TOKEN_ESTIMATE_RATIO

    def summarize_input(self, text: str, max_tokens: int = 1000) -> str:
        """Summarize a long input while preserving key information."""
        if not self.should_summarize(text):
            return text

        # Extract key components
        errors = self.ERROR_PATTERN.findall(text)
        self.STACK_TRACE_PATTERN.findall(text)
        code_blocks = self.CODE_BLOCK_PATTERN.findall(text)
        urls = self.URL_PATTERN.findall(text)

        # Build compact summary
        parts = []

        # Main content summary
        lines = text.strip().split("\n")
        key_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Keep lines with important keywords
            if any(
                kw in line.lower()
                for kw in [
                    "error",
                    "bug",
                    "fix",
                    "implement",
                    "create",
                    "update",
                    "delete",
                    "add",
                    "remove",
                    "change",
                    "modify",
                    "refactor",
                    "test",
                    "deploy",
                    "configure",
                    "setup",
                    "install",
                    "issue",
                    "problem",
                    "question",
                    "help",
                    "please",
                ]
            ):
                key_lines.append(line)

        if key_lines:
            parts.append("Key points from input:")
            for line in key_lines[:10]:
                parts.append(f"  - {line[:200]}")

        # Add errors if found
        if errors:
            parts.append("\nErrors mentioned:")
            for err in errors[:3]:
                parts.append(f"  - {err[:200]}")

        # Add code blocks (truncated)
        if code_blocks:
            parts.append(f"\nCode blocks: {len(code_blocks)} found")
            for i, block in enumerate(code_blocks[:2], 1):
                truncated = block[:500] + "..." if len(block) > 500 else block
                parts.append(f"  Block {i}:\n{truncated}")

        # Add URLs
        if urls:
            parts.append(f"\nURLs: {', '.join(urls[:5])}")

        summary = "\n".join(parts)

        # Truncate if still too long
        if self.estimate_tokens(summary) > max_tokens:
            summary = summary[: max_tokens * self.TOKEN_ESTIMATE_RATIO]

        return summary

    def extract_error_context(self, text: str) -> str:
        """Extract error context from input."""
        errors = self.ERROR_PATTERN.findall(text)
        stack_traces = self.STACK_TRACE_PATTERN.findall(text)

        if not errors and not stack_traces:
            return ""

        parts = ["Error context extracted:"]
        for err in errors[:3]:
            parts.append(f"  Error: {err[:300]}")

        if stack_traces:
            parts.append("  Stack trace references found")

        return "\n".join(parts)

    def extract_code_references(self, text: str) -> list[str]:
        """Extract code references from input."""
        code_blocks = self.CODE_BLOCK_PATTERN.findall(text)
        return [block[:200] for block in code_blocks[:5]]


class SessionCompactor:
    """Compacts long sessions while preserving important context."""

    def __init__(self, max_context_tokens: int = 4000) -> None:
        self.max_context_tokens = max_context_tokens
        self.summarizer = InputSummarizer()

    def compact_messages(
        self,
        messages: list[dict[str, Any]],
        preserve_recent: int = 10,
    ) -> CompactedContext:
        """Compact a list of messages into a summary."""
        if not messages:
            return CompactedContext(
                summary="",
                key_points=[],
                decisions=[],
                action_items=[],
                entities=[],
                original_length=0,
                compacted_length=0,
            )

        original_length = sum(len(m.get("content", "")) for m in messages)

        # Preserve recent messages
        recent_messages = messages[-preserve_recent:]
        older_messages = messages[:-preserve_recent]

        # Extract from older messages
        key_points = []
        decisions = []
        action_items = []
        entities = set()

        for msg in older_messages:
            content = msg.get("content", "")

            # Extract decisions
            if any(
                kw in content.lower()
                for kw in [
                    "decided",
                    "decision",
                    "chose",
                    "selected",
                    "agreed",
                ]
            ):
                decisions.append(content[:200])

            # Extract action items
            if any(
                kw in content.lower()
                for kw in [
                    "will",
                    "should",
                    "need to",
                    "must",
                    "todo",
                    "action",
                ]
            ):
                action_items.append(content[:200])

            # Extract key points
            if msg.get("role") == "user":
                key_points.append(content[:200])

            # Simple entity extraction
            words = content.split()
            for word in words:
                if word.startswith(("@", "#")) or word.isupper():
                    entities.add(word)

        # Build summary
        summary_parts = []
        if key_points:
            summary_parts.append(f"User discussed {len(key_points)} topics")
        if decisions:
            summary_parts.append(f"{len(decisions)} decisions were made")
        if action_items:
            summary_parts.append(f"{len(action_items)} action items identified")

        summary = "; ".join(summary_parts) if summary_parts else "Conversation session"

        # Build compacted context from recent messages
        recent_context = []
        for msg in recent_messages[-5:]:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:200]
            recent_context.append(f"{role}: {content}")

        compacted_length = len(summary) + sum(len(c) for c in recent_context)

        return CompactedContext(
            summary=summary,
            key_points=key_points[-10:],
            decisions=decisions[-5:],
            action_items=action_items[-5:],
            entities=list(entities)[:20],
            original_length=original_length,
            compacted_length=compacted_length,
        )

    def compact_with_llm(
        self,
        messages: list[dict[str, Any]],
        api_key: str = "",
        model: str = "openrouter/free",
    ) -> str:
        """Use LLM to summarize messages for better compaction."""
        if not api_key:
            import os

            api_key = os.environ.get("OPENROUTER_API_KEY", os.environ.get("OPENAI_API_KEY", ""))

        if not api_key:
            # Fallback to rule-based compaction
            compacted = self.compact_messages(messages)
            return compacted.summary

        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1", timeout=30.0)

            # Build conversation for summarization
            conversation = ""
            for msg in messages[-20:]:  # Last 20 messages
                role = msg.get("role", "user")
                content = msg.get("content", "")[:500]
                conversation += f"{role}: {content}\n"

            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Summarize this conversation concisely. "
                            "Include: key decisions, action items, current state. "
                            "Keep it under 500 words."
                        ),
                    },
                    {"role": "user", "content": conversation},
                ],
                max_tokens=1024,
                temperature=0.3,
            )
            return response.choices[0].message.content or "Summary unavailable"
        except Exception:
            compacted = self.compact_messages(messages)
            return compacted.summary

    def build_context_window(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str = "",
        max_tokens: int = 4000,
    ) -> list[dict[str, str]]:
        """Build a context window that fits within token limits."""
        context = []

        # Add system prompt
        if system_prompt:
            context.append(
                {
                    "role": "system",
                    "content": system_prompt,
                }
            )

        # Calculate remaining tokens
        system_tokens = len(system_prompt) // 4 if system_prompt else 0
        remaining_tokens = max_tokens - system_tokens

        # If few messages, include all
        if len(messages) <= 10:
            for msg in messages:
                context.append(
                    {
                        "role": msg.get("role", "user"),
                        "content": msg.get("content", ""),
                    }
                )
            return context

        # Compact older messages
        compacted = self.compact_messages(messages)

        # Add compacted context
        if compacted.summary:
            context.append(
                {
                    "role": "system",
                    "content": f"Previous context: {compacted.summary}",
                }
            )

        if compacted.decisions:
            context.append(
                {
                    "role": "system",
                    "content": f"Key decisions: {'; '.join(compacted.decisions[:3])}",
                }
            )

        # Add recent messages
        recent = messages[-8:]
        for msg in recent:
            content = msg.get("content", "")
            # Truncate if needed
            content_tokens = len(content) // 4
            if content_tokens > remaining_tokens // len(recent):
                content = content[: remaining_tokens // len(recent) * 4]

            context.append(
                {
                    "role": msg.get("role", "user"),
                    "content": content,
                }
            )

        return context

    def should_compact(self, messages: list[dict[str, Any]]) -> bool:
        """Check if messages should be compacted."""
        total_tokens = sum(len(m.get("content", "")) // 4 for m in messages)
        return total_tokens > self.max_context_tokens


@dataclass
class HierarchicalMemoryPyramid:
    """Multi-tiered structured memory pyramid for ultra-long conversations and zero-loss token compaction.

    Tier 1 (Architectural): Foundational goals, key architectural decisions, and invariants.
    Tier 2 (Delta): File modifications, touched paths, git diff summaries, and milestone statuses.
    Tier 3 (Working): High-fidelity recent message turns and active tool calls.
    """

    architectural_goals: list[str] = field(default_factory=list)
    architectural_decisions: list[str] = field(default_factory=list)
    modified_files: list[str] = field(default_factory=list)
    milestone_history: list[str] = field(default_factory=list)
    active_working_turns: list[dict[str, Any]] = field(default_factory=list)

    def record_turn(self, role: str, content: str) -> None:
        """Record turn into working tier and promote key decisions/milestones."""
        self.active_working_turns.append({"role": role, "content": content})
        # Check for goal / decision patterns
        lower = content.lower()
        if "decided to" in lower or "we will use" in lower or "chosen" in lower:
            for line in content.splitlines():
                if any(w in line.lower() for w in ("decided", "chose", "architecture", "standard")):
                    clean = line.strip(" -*#")
                    if clean and clean not in self.architectural_decisions:
                        self.architectural_decisions.append(clean[:200])

        if "goal:" in lower or "objective:" in lower:
            for line in content.splitlines():
                if "goal:" in line.lower() or "objective:" in line.lower():
                    clean = line.strip(" -*#")
                    if clean and clean not in self.architectural_goals:
                        self.architectural_goals.append(clean[:200])

    def record_file_mod(self, file_path: str) -> None:
        if file_path and file_path not in self.modified_files:
            self.modified_files.append(file_path)

    def assemble_compact_pyramid(self, max_working_turns: int = 6) -> list[dict[str, Any]]:
        """Render a token-optimized pyramid prompt context."""
        context: list[dict[str, Any]] = []

        # 1. Architectural Tier (Top of Pyramid)
        arch_lines = []
        if self.architectural_goals:
            arch_lines.append(f"• Core Goals: {'; '.join(self.architectural_goals[:3])}")
        if self.architectural_decisions:
            arch_lines.append(
                f"• Architectural Decisions: {'; '.join(self.architectural_decisions[:4])}"
            )

        if arch_lines:
            context.append(
                {
                    "role": "system",
                    "content": "[ARCHITECTURAL MEMORY PYRAMID - TIER 1]\n" + "\n".join(arch_lines),
                }
            )

        # 2. Delta Tier (Mid-Level)
        if self.modified_files:
            context.append(
                {
                    "role": "system",
                    "content": f"[WORKING DELTA - TIER 2]\nModified Files: {', '.join(self.modified_files[-12:])}",
                }
            )

        # 3. Working Tier (Base of Pyramid - High Fidelity)
        recent_turns = self.active_working_turns[-max_working_turns:]
        for turn in recent_turns:
            context.append({"role": turn.get("role", "user"), "content": turn.get("content", "")})

        return context
