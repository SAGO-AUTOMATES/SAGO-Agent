"""Tri-Partite Context Assembly & Smart Prompting Pipeline.

Implements the multi-tiered context assembly pipeline specified in docs/FLOWS.md:
1. Structural Outline (AST Symbol Graph & Project Graph)
2. Hybrid BM25 & Semantic Vector Search / RAG Memory
3. 3-Tier Hierarchical Memory Pyramid & Working Deltas
4. Persistent Learning Store (Past Successes, Failures & Error Fixes)
5. Cross-Session Database History
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from sago.learning import get_learning_store
from sago.memory.compaction import HierarchicalMemoryPyramid
from sago.memory.project_instructions import get_project_instructions
from sago.utils.errors import log_error
from sago.utils.safe import log_exception

logger = logging.getLogger("sago.engine.context_assembler")


class _TokenBudget:
    """Simple token budget tracker with priority-based truncation."""

    def __init__(self, max_tokens: int = 12000) -> None:
        self.max_tokens = max_tokens
        self.used = 0

    def remaining(self) -> int:
        return max(0, self.max_tokens - self.used)

    def can_add(self, estimated_tokens: int) -> bool:
        return self.used + estimated_tokens <= self.max_tokens

    def consume(self, text: str, ratio: float = 4.0) -> bool:
        """Estimate tokens and consume budget. Returns True if within budget."""
        estimated = int(len(text) / ratio)
        if self.used + estimated > self.max_tokens:
            # Truncate to fit
            available_chars = int(self.remaining() * ratio)
            if available_chars > 100:
                truncated = text[:available_chars] + "... [truncated for token budget]"
                self.used += int(len(truncated) / ratio)
                return True
            return False
        self.used += estimated
        return True

    def consume_strict(self, text: str, ratio: float = 4.0) -> str:
        """Consume budget and return truncated text if needed."""
        estimated = int(len(text) / ratio)
        if self.used + estimated <= self.max_tokens:
            self.used += estimated
            return text
        available_chars = int(self.remaining() * ratio)
        if available_chars > 100:
            result = text[:available_chars] + "... [truncated for token budget]"
            self.used += int(len(result) / ratio)
            return result
        self.used = self.max_tokens
        return ""


@dataclass
class AssembledContext:
    """Structured assembled context ready for agent prompt construction."""

    project_summary: str = ""
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    ast_symbols_context: str = ""
    rag_snippets_context: str = ""
    memory_pyramid_context: str = ""
    learning_approach: str = ""
    known_fixes: list[str] = field(default_factory=list)
    past_session_context: str = ""
    project_instructions: str = ""
    handoff_targets: list[str] = field(default_factory=list)

    def format_user_context_block(self) -> str:
        """Format data context blocks safely for injection into the user prompt."""
        sections = []

        if self.project_summary:
            sections.append(f"### Project Structure & Environment\n{self.project_summary}")

        if self.ast_symbols_context:
            sections.append(f"### Relevant Symbols & Code Outline\n{self.ast_symbols_context}")

        if self.rag_snippets_context:
            sections.append(
                f"### Relevant Code Snippets & Documentation\n{self.rag_snippets_context}"
            )

        if self.past_session_context:
            sections.append(f"### Context from Prior Sessions\n{self.past_session_context}")

        return "\n\n".join(sections)

    def format_system_enhancements(self) -> str:
        """Format trusted system-level enhancements (instructions, learnings, pyramid)."""
        sections = []

        if self.memory_pyramid_context:
            sections.append(f"=== HIERARCHICAL MEMORY PYRAMID ===\n{self.memory_pyramid_context}")

        if self.learning_approach:
            sections.append(
                f"=== PAST SUCCESSFUL APPROACH ===\n"
                f"Based on proven strategies from previous sessions:\n"
                f"{self.learning_approach}\n"
                f"Adopt a similar verified pattern where appropriate."
            )

        if self.known_fixes:
            fixes_text = "\n".join(f"• {f}" for f in self.known_fixes[:3])
            sections.append(f"=== VERIFIED ERROR FIXES ===\n{fixes_text}")

        if self.project_instructions:
            sections.append(self.project_instructions)

        if self.handoff_targets:
            targets_str = "\n".join(self.handoff_targets)
            sections.append(
                f"=== AUTHORIZED AGENT HANDOFF TARGETS ===\n"
                f"When your solution requires specialized domain expertise (code review, security audit, qa tests, cloud deployment), "
                f"you can hand off or delegate tasks to peer specialist agents using the `spawn_agent` tool:\n"
                f"{targets_str}"
            )

        return "\n\n".join(sections)


class ContextAssembler:
    """Assembles rich, multi-tiered context prior to agent prompting."""

    def __init__(self, cwd: str | None = None) -> None:
        self.cwd = Path(cwd) if cwd else Path.cwd()

    def assemble(
        self,
        task: str,
        task_type: str = "create",
        agent_name: str | None = None,
        available_tools: list[str] | None = None,
        pyramid: HierarchicalMemoryPyramid | None = None,
        session_id: str = "default",
        max_symbols: int = 8,
        max_rag_snippets: int = 3,
        max_tokens: int = 12000,
    ) -> AssembledContext:
        """Assemble comprehensive context for a task following the 5-layer pipeline."""
        ctx = AssembledContext()
        if task_type == "chat":
            # For casual conversation, greetings, weather — skip heavy context assembly.
            # "query" is NOT short-circuited here because queries like "analyze my repo"
            # need AST symbols, project graph, and structural context.
            return ctx
        # Summary intent short-circuit — reuse cached analysis, do NOT waste tokens on heavy search/RAG
        # Detect via spec regex r"\b(summar|what was done|what did you do)\b" plus typo tolerance
        # Avoid false-positive on file-specific "summarize this file" (needs heavy context)
        _low = task.lower() if task else ""
        _has_file_hint = bool(
            re.search(
                r"\b[\w\-/\\.]+\.(?:py|js|ts|tsx|jsx|md|txt|json|yaml|yml|toml|html|css|java|go|rs|c|cpp|h|rb|php|sh|sql)\b",
                _low,
            )
            or "#file" in _low
            or "this file" in _low
            or "the file" in _low
        )
        _is_summary = False
        if task_type == "summary":
            _is_summary = True
        elif re.search(r"\b(summar|what was done|what did you do)\b", _low):
            _is_summary = True
        elif ("summar" in _low or "sumam" in _low) and not _has_file_hint:
            _is_summary = True
        elif "sumam" in _low:
            _is_summary = True
        # File-specific summarize should NOT short-circuit unless explicitly about prior work
        if (
            _is_summary
            and _has_file_hint
            and not re.search(r"\b(what you did|what was done|what did you do)\b", _low)
        ):
            _is_summary = False
        if _is_summary:
            logger.debug("Summary intent detected — skipping heavy context assembly (0 search/RAG)")
            return ctx

        token_budget = _TokenBudget(max_tokens)

        # 1. Detect project structure, languages, frameworks
        try:
            from sago.engine.simple_executor import _detect_project_context, _get_context

            base_ctx = _get_context(str(self.cwd))
            p_info = _detect_project_context(str(self.cwd))
            ctx.languages = p_info.get("languages", [])
            ctx.frameworks = p_info.get("frameworks", [])

            summary_lines = [base_ctx]
            if ctx.languages:
                summary_lines.append(f"Languages: {', '.join(ctx.languages)}")
            if ctx.frameworks:
                summary_lines.append(f"Frameworks: {', '.join(ctx.frameworks)}")

            # Check if query is architectural or codebase structure-oriented
            arch_keywords = {
                # Existing
                "architecture",
                "arch",
                "graph",
                "map",
                "topology",
                "structure",
                "subsystem",
                "pipeline",
                "flow",
                "models",
                "dependencies",
                "overview",
                "explain",
                "codebase",
                "layout",
                # Analysis / review
                "analyze",
                "analysis",
                "review",
                "audit",
                "inspect",
                "examine",
                "understand",
                "describe",
                "explore",
                "investigate",
                # Project / repo
                "repo",
                "repository",
                "project",
                "code",
                "source",
                # Visualization
                "diagram",
                "visualize",
                "chart",
                "visual",
                # How / what questions about code
                "how",
                "what",
                "where",
                "which",
                "about",
            }
            task_words = set(re.findall(r"[a-zA-Z]{3,}", task.lower()))
            if task_words & arch_keywords:
                try:
                    from sago.memory.project_graph import get_cached_project_graph

                    pg = get_cached_project_graph(root_dir=self.cwd, max_files=400)
                    hub_summary = pg.to_llm_context()
                    if hub_summary:
                        summary_lines.append(
                            f"\nCodebase Topology ({len(pg.nodes)} components, {len(pg.edges)} relations):\n{hub_summary[:800]}"
                        )
                except Exception as e:
                    log_exception(e, "Project graph topology summary")

            ctx.project_summary = token_budget.consume_strict("\n".join(summary_lines))
        except Exception as e:
            log_error("ContextAssembler: project summary failed", e)

        # 2. Extract AST Symbols & Topology relevant to query
        try:
            from sago.memory.symbol_graph import SymbolGraph

            sg = SymbolGraph(root_dir=str(self.cwd))
            task_words = set(re.findall(r"[a-zA-Z0-9_]{3,}", task.lower()))
            matching_symbols = []

            # Match files or outline nodes
            outline = sg.get_symbol_outline(max_files=50)
            for file_path, symbols in outline.items():
                for sym in symbols:
                    sym_name = sym.get("name", "")
                    if any(t in sym_name.lower() or t in file_path.lower() for t in task_words):
                        matching_symbols.append(
                            f"• `{sym.get('kind', 'symbol')}` {sym_name} in {file_path}:{sym.get('line', 1)}"
                        )
                        if len(matching_symbols) >= max_symbols:
                            break
                if len(matching_symbols) >= max_symbols:
                    break

            # Fallback: if no word-level matches, return top hub files (most connected)
            if not matching_symbols and outline:
                hub_files = sorted(
                    outline.keys(),
                    key=lambda f: len(outline[f]),
                    reverse=True,
                )[:max_symbols]
                for fp in hub_files:
                    syms = outline[fp]
                    sym_names = [s.get("name", "?") for s in syms[:3]]
                    matching_symbols.append(
                        f"• `{fp}` — {', '.join(sym_names)}{'...' if len(syms) > 3 else ''}"
                    )

            if matching_symbols:
                ctx.ast_symbols_context = token_budget.consume_strict("\n".join(matching_symbols))
        except Exception as e:
            log_error("ContextAssembler: AST symbol extraction failed", e)

        # 3. Hybrid Code Search / RAG Context
        try:
            from sago.memory.hybrid_indexer import get_hybrid_code_indexer

            indexer = get_hybrid_code_indexer(str(self.cwd))
            # Fast query for relevant code chunks
            results = indexer.search(task, limit=max_rag_snippets)
            snippets = []
            for r in results:
                # HybridSearchResult stores data in r.chunk (HybridCodeChunk)
                chunk = r.chunk
                fp = chunk.file_path if chunk else ""
                snippet = chunk.content if chunk else ""
                score = r.combined_score if hasattr(r, "combined_score") else 0.0
                if fp and snippet:
                    clean_snippet = snippet.strip()[:300]
                    snippet_text = f"File `{fp}` (score: {score:.2f}):\n```\n{clean_snippet}\n```"
                    if token_budget.consume(snippet_text):
                        snippets.append(snippet_text)

            if snippets:
                ctx.rag_snippets_context = "\n\n".join(snippets)
        except Exception as e:
            log_error("ContextAssembler: Hybrid code search failed", e)

        # 4. Hierarchical Memory Pyramid Context
        if pyramid:
            try:
                pyramid_parts = []
                if pyramid.architectural_goals:
                    pyramid_parts.append(f"Goals: {'; '.join(pyramid.architectural_goals[:3])}")
                if pyramid.architectural_decisions:
                    pyramid_parts.append(
                        f"Decisions: {'; '.join(pyramid.architectural_decisions[:3])}"
                    )
                if pyramid.modified_files:
                    pyramid_parts.append(
                        f"Modified Files: {', '.join(pyramid.modified_files[-8:])}"
                    )
                if pyramid.semantic_summary:
                    pyramid_parts.append(f"Prior Progress: {pyramid.semantic_summary[:300]}")
                if pyramid_parts:
                    pyramid_text = "\n".join(pyramid_parts)
                    if token_budget.consume(pyramid_text):
                        ctx.memory_pyramid_context = pyramid_text
            except Exception as e:
                log_error("ContextAssembler: Memory pyramid extraction failed", e)

        # 5. Learning Store (Successes, Known Fixes & Strategies)
        try:
            ls = get_learning_store()
            tools_list = available_tools or []
            suggestion = ls.suggest_approach(task_type, tools_list)
            if suggestion and token_budget.consume(suggestion):
                ctx.learning_approach = suggestion

            fixes = ls.get_known_fixes(task)
            if fixes:
                fix_list = [fixes] if isinstance(fixes, str) else list(fixes)
                # Budget: keep only fixes that fit
                budget_fixes = []
                for fix in fix_list:
                    if token_budget.consume(fix):
                        budget_fixes.append(fix)
                    else:
                        break
                ctx.known_fixes = budget_fixes
        except Exception as e:
            log_error("ContextAssembler: Learning store query failed", e)

        # 6. Past Sessions History from SQLite Database
        try:
            from sago.database import MessageStore, init_db

            init_db()
            msg_store = MessageStore(session_id)
            past_messages = msg_store.get_history(limit=4)
            if past_messages:
                turns = []
                for m in past_messages:
                    r = m.get("role", "user")
                    c = m.get("content", "")[:200]
                    if c:
                        turn = f"{r.title()}: {c}"
                        if token_budget.consume(turn):
                            turns.append(turn)
                if turns:
                    ctx.past_session_context = "\n".join(turns)
        except Exception as e:
            log_error("ContextAssembler: Past session history lookup failed", e)

        # 7. Project Instructions (CLAUDE.md / .sago/instructions.md)
        try:
            pi = get_project_instructions(str(self.cwd))
            prompt_instr = pi.get_for_prompt()
            if prompt_instr:
                ctx.project_instructions = prompt_instr
        except Exception as e:
            log_error("ContextAssembler: Project instructions lookup failed", e)

        # 8. Authorized Handoff Targets for Agent
        if agent_name:
            try:
                from sago.agents.registry import get_handoff_targets

                targets = get_handoff_targets(agent_name)
                if targets:
                    ctx.handoff_targets = [
                        f"• `{t.name}` ({t.role}): {t.description[:100]}" for t in targets[:8]
                    ]
            except Exception as e:
                log_error("ContextAssembler: Handoff targets resolution failed", e)

        return ctx


_assembler_instance: ContextAssembler | None = None


def get_context_assembler(cwd: str | None = None) -> ContextAssembler:
    """Get or create the global ContextAssembler instance."""
    global _assembler_instance
    if _assembler_instance is None or (
        cwd and str(_assembler_instance.cwd) != str(Path(cwd).resolve())
    ):
        _assembler_instance = ContextAssembler(cwd)
    return _assembler_instance
