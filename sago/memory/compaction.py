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


@dataclass(frozen=True)
class CompactionThresholds:
    """Dynamic context compaction thresholds based on model and provider capabilities."""

    tier: str  # "local", "standard", "massive"
    trigger_tokens: int  # token threshold when compaction should automatically trigger
    target_tokens: int  # target budget when pruning context
    trigger_messages: int  # message turn guard threshold
    description: str  # human-readable badge / description

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier,
            "trigger_tokens": self.trigger_tokens,
            "target_tokens": self.target_tokens,
            "trigger_messages": self.trigger_messages,
            "description": self.description,
        }


def resolve_dynamic_context_window(
    provider: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    context_window: int | None = None,
) -> tuple[int, str]:
    """Dynamically determine model context window and tier without rigid model binding.

    Returns:
        (context_window_tokens, tier_name)
    """
    import os
    import re

    if context_window and context_window > 0:
        if context_window >= 500_000:
            return context_window, "massive"
        if context_window <= 128_000:
            return context_window, "local"
        return context_window, "standard"

    # Environment override
    env_cw = os.environ.get("SAGO_CONTEXT_WINDOW")
    if env_cw and env_cw.isdigit():
        val = int(env_cw)
        tier = "massive" if val >= 500_000 else ("local" if val <= 128_000 else "standard")
        return val, tier

    prov_str = (provider or "").lower().strip()
    model_str = (model or "").lower().strip()
    base_str = (base_url or "").lower().strip()

    if not prov_str or not model_str:
        try:
            from sago.llm.tui_providers import resolve_active_llm_config

            active_cfg = resolve_active_llm_config(
                provider=provider, model=model, base_url=base_url
            )
            if not prov_str:
                prov_str = (active_cfg.get("provider") or "").lower().strip()
            if not model_str:
                model_str = (active_cfg.get("model") or "").lower().strip()
            if not base_str:
                base_str = (active_cfg.get("base_url") or "").lower().strip()
        except Exception:
            pass

    # Dynamic extraction of context size suffix (e.g., -128k, :200k, -1m, :32k, etc.)
    ctx_match = re.search(r"(?:^|[-_:/])(\d+)(k|m)(?:$|[-_:/])", model_str)
    if ctx_match:
        val = int(ctx_match.group(1))
        unit = ctx_match.group(2)
        extracted = val * 1_000_000 if unit == "m" else val * 1_000
        tier = (
            "massive" if extracted >= 500_000 else ("local" if extracted <= 128_000 else "standard")
        )
        return extracted, tier

    # Dynamic local runtime check
    is_local = (
        prov_str in ("ollama", "lmstudio", "local", "mock")
        or "localhost" in base_str
        or "127.0.0.1" in base_str
        or "local" in model_str
        or "gguf" in model_str
        or "ollama" in model_str
    )
    if not is_local:
        try:
            from sago.llm.registry import get_provider_spec

            spec = get_provider_spec(prov_str)
            if spec and spec.local:
                is_local = True
        except Exception:
            pass

    if is_local:
        return 100_000, "local"

    # Massive context check
    if prov_str in ("google", "gemini") or "gemini" in model_str or "massive" in model_str:
        return 1_000_000, "massive"

    # Default cloud standard
    return 200_000, "standard"


def get_dynamic_compaction_thresholds(
    provider: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    context_window: int | None = None,
) -> CompactionThresholds:
    """Determine dynamic compaction thresholds based on provider/model capabilities.

    Tiers:
    1. Local models (Ollama, LM Studio, local models, etc.):
       - Range: 50k to 100k tokens
       - Default trigger: 75,000 tokens (~300k chars) or 20+ messages
       - Pruned target: 35,000 tokens
       - Configurable via SAGO_COMPACTION_THRESHOLD_LOCAL

    2. Standard Cloud models (Claude 3.5 Sonnet, GPT-4o, DeepSeek, Groq, Mistral, OpenRouter default):
       - Range: 150k to 200k tokens
       - Default trigger: 175,000 tokens (~700k chars) or 45+ messages
       - Pruned target: 80,000 tokens
       - Configurable via SAGO_COMPACTION_THRESHOLD_STANDARD

    3. Massive Context models (Gemini 1.5/2.0/2.5 Pro/Flash, Claude 1M, Qwen 1M, models with >= 1M context):
       - Range: 750k to 1M tokens
       - Default trigger: 750,000 tokens (~3,000,000 chars) or 120+ messages
       - Pruned target: 250,000 tokens
       - Configurable via SAGO_COMPACTION_THRESHOLD_MASSIVE

    Global override: SAGO_COMPACTION_THRESHOLD or SAGO_MAX_TOKENS.
    """
    import os

    # Global explicit overrides take precedence if set
    global_override = os.environ.get("SAGO_COMPACTION_THRESHOLD") or os.environ.get(
        "SAGO_MAX_TOKENS"
    )
    global_tokens = int(global_override) if global_override and global_override.isdigit() else None

    cw, tier = resolve_dynamic_context_window(
        provider=provider,
        model=model,
        base_url=base_url,
        context_window=context_window,
    )

    # 1. Local Tier: 50k to 100k (scaled down gracefully for sub-64k context windows)
    if tier == "local":
        env_val = os.environ.get("SAGO_COMPACTION_THRESHOLD_LOCAL")
        if cw and cw < 64_000:
            default_trig = max(2_000, int(cw * 0.75))
        else:
            default_trig = min(100_000, max(50_000, int(cw * 0.75))) if cw else 75_000
        trigger = int(env_val) if env_val and env_val.isdigit() else (global_tokens or default_trig)
        target = min(35_000, max(1_000, int(trigger * 0.45)))
        return CompactionThresholds(
            tier="local",
            trigger_tokens=trigger,
            target_tokens=target,
            trigger_messages=20,
            description=f"Local model tier ({cw // 1000}k window: {trigger // 1000}k trigger)",
        )

    # 2. Massive Context Tier (1M+ context window): 750k to 1M
    if tier == "massive":
        env_val = os.environ.get("SAGO_COMPACTION_THRESHOLD_MASSIVE")
        default_trig = min(1_000_000, max(750_000, int(cw * 0.75))) if cw else 750_000
        trigger = int(env_val) if env_val and env_val.isdigit() else (global_tokens or default_trig)
        target = min(250_000, int(trigger * 0.35))
        return CompactionThresholds(
            tier="massive",
            trigger_tokens=trigger,
            target_tokens=target,
            trigger_messages=120,
            description=f"Massive context tier ({cw // 1000}k window: {trigger // 1000}k trigger)",
        )

    # 3. Standard Cloud Tier: 150k to 200k
    env_val = os.environ.get("SAGO_COMPACTION_THRESHOLD_STANDARD")
    default_trig = min(200_000, max(150_000, int(cw * 0.875))) if cw else 175_000
    trigger = int(env_val) if env_val and env_val.isdigit() else (global_tokens or default_trig)
    target = min(80_000, int(trigger * 0.45))
    return CompactionThresholds(
        tier="standard",
        trigger_tokens=trigger,
        target_tokens=target,
        trigger_messages=45,
        description=f"Standard cloud tier ({cw // 1000}k window: {trigger // 1000}k trigger)",
    )


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

    def __init__(
        self,
        max_context_tokens: int | None = None,
        provider: str | None = None,
        model: str | None = None,
        context_window: int | None = None,
    ) -> None:
        if max_context_tokens is not None:
            self.max_context_tokens = max_context_tokens
            self.thresholds: CompactionThresholds | None = None
        else:
            self.thresholds = get_dynamic_compaction_thresholds(
                provider=provider, model=model, context_window=context_window
            )
            self.max_context_tokens = self.thresholds.trigger_tokens
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
        files_mentioned = set()

        file_pat = re.compile(
            r"\b([\w\-./]+\.(?:py|js|ts|jsx|tsx|go|rs|java|c|cpp|md|json|toml|sql))\b"
        )

        for msg in older_messages:
            content = msg.get("content", "")
            for f in file_pat.findall(content):
                if not f.startswith("http") and not f.endswith(".min.js"):
                    files_mentioned.add(f)

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
                clean_kp = content.strip().splitlines()[0][:120]
                if clean_kp and not clean_kp.startswith("/"):
                    key_points.append(clean_kp)

            # Simple entity extraction
            words = content.split()
            for word in words:
                if word.startswith(("@", "#")) or word.isupper():
                    entities.add(word)

        # Build summary
        summary_parts = []
        if key_points:
            summary_parts.append(f"Goals: {'; '.join(key_points[-3:])}")
        if files_mentioned:
            summary_parts.append(f"Files touched: {', '.join(sorted(files_mentioned)[:5])}")
        if decisions:
            summary_parts.append(
                f"Decisions: {'; '.join(d.splitlines()[0][:80] for d in decisions[-2:])}"
            )

        summary = " | ".join(summary_parts) if summary_parts else "Conversation session"

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
