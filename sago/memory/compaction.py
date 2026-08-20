"""Input Summarization and Compaction

Handles long inputs by summarizing before processing to save tokens.
Provides session compaction for maintaining context in long conversations.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("sago.memory.compaction")


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
        result = word_count > self.WORD_THRESHOLD
        logger.debug(
            "should_summarize: word_count=%d, threshold=%d, result=%s",
            word_count,
            self.WORD_THRESHOLD,
            result,
        )
        return result

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count."""
        return len(text) // self.TOKEN_ESTIMATE_RATIO

    def summarize_input(self, text: str, max_tokens: int = 1000) -> str:
        """Summarize a long input while preserving key information."""
        if not self.should_summarize(text):
            logger.debug(
                "Input below threshold, skipping summarization (%d tokens)",
                self.estimate_tokens(text),
            )
            return text

        logger.info(
            "Summarizing input: %d chars, ~%d tokens", len(text), self.estimate_tokens(text)
        )

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
            logger.debug("Truncated summary to %d chars (~%d tokens)", len(summary), max_tokens)

        logger.info(
            "Summarized: %d chars -> %d chars (ratio=%.1f%%)",
            len(text),
            len(summary),
            (1 - len(summary) / len(text)) * 100 if text else 0,
        )
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
        logger.info("Compacting %d messages (preserve_recent=%d)", len(messages), preserve_recent)
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

        result = CompactedContext(
            summary=summary,
            key_points=key_points[-10:],
            decisions=decisions[-5:],
            action_items=action_items[-5:],
            entities=list(entities)[:20],
            original_length=original_length,
            compacted_length=compacted_length,
        )
        logger.info(
            "Compaction result: original=%d, compacted=%d, ratio=%.1f%%",
            original_length,
            compacted_length,
            result.compression_ratio * 100,
        )
        logger.debug(
            "Decisions=%d, action_items=%d, entities=%d",
            len(decisions),
            len(action_items),
            len(entities),
        )
        return result

    def compact_with_llm(
        self,
        messages: list[dict[str, Any]],
        api_key: str = "",
        model: str = "openrouter/free",
    ) -> str:
        """Use LLM to summarize messages for better compaction."""
        try:
            from sago.llm.tui_providers import get_tui_client, resolve_active_llm_config

            active_cfg = resolve_active_llm_config(
                model=None if model == "openrouter/free" else model,
                api_key=api_key or None,
            )
            if not api_key:
                api_key = active_cfg["api_key"]
            if model == "openrouter/free" and active_cfg["model"]:
                model = active_cfg["model"]
            provider = active_cfg["provider"]
        except Exception:
            logger.exception("Failed to resolve LLM config for compaction")
            return self.compact_messages(messages).summary

        if not api_key:
            logger.warning("No API key available, falling back to rule-based compaction")
            compacted = self.compact_messages(messages)
            return compacted.summary

        try:
            from sago.llm.tui_providers import get_tui_client

            logger.info(
                "Calling LLM summarization: provider=%s model=%s messages=%d",
                provider,
                model,
                len(messages),
            )
            client, api_model = get_tui_client(provider, model)

            # Build conversation for summarization
            conversation = ""
            for msg in messages[-20:]:  # Last 20 messages
                role = msg.get("role", "user")
                content = msg.get("content", "")[:500]
                conversation += f"{role}: {content}\n"

            summary_prompt = (
                "Summarize this conversation concisely. "
                "Include: key decisions, action items, current state. "
                "Keep it under 500 words."
            )

            if provider == "google":
                from google.genai import types as google_types

                contents = [
                    google_types.Content(
                        role="user",
                        parts=[google_types.Part(text=f"{summary_prompt}\n\n{conversation}")],
                    )
                ]
                response = client.models.generate_content(
                    model=api_model,
                    contents=contents,
                    config=google_types.GenerateContentConfig(
                        max_output_tokens=1024, temperature=0.3
                    ),
                )
                result = response.text or "Summary unavailable"
            else:
                response = client.chat.completions.create(
                    model=api_model,
                    messages=[
                        {"role": "system", "content": summary_prompt},
                        {"role": "user", "content": conversation},
                    ],
                    max_tokens=1024,
                    temperature=0.3,
                )
                result = response.choices[0].message.content or "Summary unavailable"
            logger.info("LLM summarization complete: %d chars returned", len(result))
            return result
        except Exception as e:
            logger.error("LLM summarization failed, falling back to rule-based: %s", e)
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

        # Preserve architectural goals/decisions and modified files across
        # compaction via the hierarchical memory pyramid (tiers 1 & 2), so
        # long-range context is not lost when naive summarization runs.
        structural = self._pyramid_structural_context(messages)
        if structural:
            context.append(structural)

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

    def _pyramid_structural_context(self, messages: list[dict[str, Any]]) -> dict[str, str] | None:
        """Build a structural (tier 1 + tier 2) memory block from the conversation.

        Uses the hierarchical memory pyramid to retain architectural goals, key
        decisions, and modified files across compaction. Working-tier turns are
        intentionally excluded here to avoid duplicating the recent messages that
        are appended separately.
        """
        try:
            pyramid = HierarchicalMemoryPyramid()
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if isinstance(content, str):
                    pyramid.record_turn(role, content)

            tier = pyramid.assemble_compact_pyramid(max_working_turns=0)
            if not tier:
                return None

            return {
                "role": "system",
                "content": "\n".join(block["content"] for block in tier),
            }
        except Exception:
            return None

    def should_compact(self, messages: list[dict[str, Any]]) -> bool:
        """Check if messages should be compacted."""
        total_tokens = sum(len(m.get("content", "")) // 4 for m in messages)
        result = total_tokens > self.max_context_tokens
        logger.debug(
            "should_compact: total_tokens=%d, max=%d, result=%s",
            total_tokens,
            self.max_context_tokens,
            result,
        )
        return result


@dataclass
class HierarchicalMemoryPyramid:
    """Multi-tiered structured memory pyramid for ultra-long conversations and zero-loss token compaction.

    Tier 1 (Architectural): Foundational goals, key architectural decisions, and invariants.
    Tier 2 (Delta): File modifications, touched paths, git diff summaries, and milestone statuses.
    Tier 3 (Semantic Summary): Extractive / LLM summarization of working turns into a compact
        narrative of "what happened" — the first real distillation layer.
    Tier 4 (Deep Distillation): A synthesized, coherent distillation combining tiers 1-3 into a
        single long-range context paragraph that survives aggressive compaction.
    Base (Working): High-fidelity recent message turns and active tool calls.
    """

    architectural_goals: list[str] = field(default_factory=list)
    architectural_decisions: list[str] = field(default_factory=list)
    modified_files: list[str] = field(default_factory=list)
    milestone_history: list[str] = field(default_factory=list)
    active_working_turns: list[dict[str, Any]] = field(default_factory=list)
    semantic_summary: str = ""
    deep_distillation: str = ""
    summarizer: Callable[[str, str], str] | None = field(default=None, repr=False)

    # Stopwords used by the deterministic extractive fallback summarizer.
    _STOPWORDS: frozenset[str] = frozenset(
        (
            "the a an and or but to of in on for with is are was were be been this that it as "
            "at by from we you i he she they them his her our your their will would should could "
            "can may might must do does did has have had not no yes if then else when while about "
            "into out up down over under again more most other some such only own same than too "
            "very can't don't won't"
        ).split()
    )

    def record_turn(self, role: str, content: str) -> None:
        """Record turn into working tier and promote key decisions/milestones."""
        self.active_working_turns.append({"role": role, "content": content})
        # Invalidate any cached distillation so the next assemble re-derives it.
        self.semantic_summary = ""
        self.deep_distillation = ""
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

        # Promote milestone / completion markers to the delta tier.
        if any(kw in lower for kw in ("milestone:", "completed", "done:", "finished", "shipped")):
            for line in content.splitlines():
                if any(
                    kw in line.lower()
                    for kw in ("milestone:", "completed", "done:", "finished", "shipped")
                ):
                    clean = line.strip(" -*#")
                    if clean and clean not in self.milestone_history:
                        self.milestone_history.append(clean[:200])

    def record_file_mod(self, file_path: str) -> None:
        if file_path and file_path not in self.modified_files:
            self.modified_files.append(file_path)

    def distill(self) -> None:
        """Populate the upper-tier (semantic + deep) distillation layers.

        Uses ``self.summarizer`` (an LLM-backed callable if provided) and otherwise
        falls back to a deterministic, network-free extractive summarizer so the
        output is stable and testable.
        """
        if self.semantic_summary and self.deep_distillation:
            return

        turns_text = "\n".join(str(t.get("content", "")) for t in self.active_working_turns).strip()
        if not turns_text:
            return

        if self.summarizer is not None:
            self.semantic_summary = self.summarizer(turns_text, "semantic")
            source = self._deep_distill_source()
            self.deep_distillation = self.summarizer(source, "deep")
        else:
            self.semantic_summary = self._extractive_summarize(turns_text)
            self.deep_distillation = self._deep_distill()

    @staticmethod
    def _extractive_summarize(text: str, max_sentences: int = 6, max_chars: int = 800) -> str:
        """Deterministic extractive summarizer: keep the highest-signal sentences.

        Scores sentences by summed content-word frequency across the turn text so
        the result is reproducible without any network or model dependency.
        """
        sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
        sentences = [s.strip() for s in sentences if s.strip()]
        if not sentences:
            return ""

        if len(sentences) <= max_sentences:
            summary = " ".join(sentences)
        else:
            words = re.findall(r"[a-zA-Z0-9_]+", text.lower())
            freq: dict[str, int] = {}
            for w in words:
                if w not in HierarchicalMemoryPyramid._STOPWORDS and len(w) > 2:
                    freq[w] = freq.get(w, 0) + 1

            def score(sentence: str) -> int:
                return sum(
                    freq.get(w, 0)
                    for word in re.findall(r"[a-zA-Z0-9_]+", sentence.lower())
                    for w in (word,)
                )

            ranked = sorted(sentences, key=score, reverse=True)
            summary = " ".join(ranked[:max_sentences])

        return summary[:max_chars].strip()

    def _deep_distill_source(self) -> str:
        """Assemble the source text fed into the deep-distillation layer."""
        parts: list[str] = []
        if self.architectural_goals:
            parts.append("Goals: " + "; ".join(self.architectural_goals[:3]))
        if self.architectural_decisions:
            parts.append("Decisions: " + "; ".join(self.architectural_decisions[:4]))
        if self.semantic_summary:
            parts.append("Semantic summary: " + self.semantic_summary)
        if self.modified_files:
            parts.append("Files: " + ", ".join(self.modified_files[-8:]))
        if self.milestone_history:
            parts.append("Milestones: " + "; ".join(self.milestone_history[:4]))
        return "\n".join(parts)

    def _deep_distill(self) -> str:
        """Build a coherent single-paragraph deep distillation from lower tiers."""
        parts: list[str] = []
        if self.architectural_goals:
            parts.append("Project aims to " + "; ".join(self.architectural_goals[:3]) + ".")
        if self.architectural_decisions:
            parts.append("Key decisions: " + "; ".join(self.architectural_decisions[:4]) + ".")
        if self.semantic_summary:
            parts.append("Recent work: " + self.semantic_summary)
        if self.modified_files:
            parts.append("Files in play: " + ", ".join(self.modified_files[-8:]) + ".")
        if self.milestone_history:
            parts.append("Milestones reached: " + "; ".join(self.milestone_history[:3]) + ".")
        return " ".join(parts).strip()

    def assemble_compact_pyramid(self, max_working_turns: int = 6) -> list[dict[str, Any]]:
        """Render a token-optimized pyramid prompt context including upper tiers."""
        self.distill()

        context: list[dict[str, Any]] = []

        # 1. Architectural Tier (Top of Pyramid)
        arch_lines = []
        if self.architectural_goals:
            arch_lines.append(f"• Core Goals: {'; '.join(self.architectural_goals[:3])}")
        if self.architectural_decisions:
            arch_lines.append(
                f"• Architectural Decisions: {'; '.join(self.architectural_decisions[:4])}"
            )
        if self.milestone_history:
            arch_lines.append(f"• Milestones: {'; '.join(self.milestone_history[:4])}")

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

        # 3. Semantic Summary Tier (first real distillation layer)
        if self.semantic_summary:
            context.append(
                {
                    "role": "system",
                    "content": f"[SEMANTIC SUMMARY - TIER 3]\n{self.semantic_summary}",
                }
            )

        # 4. Deep Distillation Tier (coherent long-range context)
        if self.deep_distillation:
            context.append(
                {
                    "role": "system",
                    "content": f"[DEEP DISTILLATION - TIER 4]\n{self.deep_distillation}",
                }
            )

        # Base: Working Tier (High Fidelity recent turns)
        recent_turns = self.active_working_turns[-max_working_turns:]
        for turn in recent_turns:
            context.append({"role": turn.get("role", "user"), "content": turn.get("content", "")})

        return context
