"""Intelligent Prompt Enhancer & Intent Clarity Synthesizer for SAGO.

Automatically expands, clarifies, structures, and optimizes user prompts before
delegating tasks to specialist agents, execution chains, or feedback loops.

Users do not need to write 'perfect prompts' — SAGO extracts core intent, injects
workspace context and constraints, defines explicit acceptance criteria, and provides
full transparency by displaying the enhanced prompt and recording dev trace events.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sago.tracking.dev_tracer import TraceEventType, get_dev_tracer

logger = logging.getLogger("sago.engine.prompt_enhancer")


@dataclass
class PromptEnhancementResult:
    """Structured result from prompt enhancement."""

    original_prompt: str
    enhanced_prompt: str
    intent_summary: str
    target_scope: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    operational_constraints: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    was_modified: bool = True
    agent_role: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_prompt": self.original_prompt,
            "enhanced_prompt": self.enhanced_prompt,
            "intent_summary": self.intent_summary,
            "target_scope": self.target_scope,
            "acceptance_criteria": self.acceptance_criteria,
            "operational_constraints": self.operational_constraints,
            "improvements": self.improvements,
            "was_modified": self.was_modified,
            "agent_role": self.agent_role,
            "timestamp": self.timestamp,
        }

    def format_cli_summary(self) -> str:
        """Format a concise human-readable summary for CLI / TUI."""
        tags = " • ".join(self.improvements[:4])
        return (
            f"[bold cyan]✨ Prompt Automatically Enhanced[/bold cyan] [dim]({tags})[/dim]\n"
            f"[dim]Intent:[/] [white]{self.intent_summary}[/white]"
        )


class PromptEnhancer:
    """Intelligent prompt synthesizer and clarifier."""

    # Action intent patterns
    _INTENT_MAP = {
        "bug_fix": (
            r"\b(fix|bug|error|broken|crash|issue|patch|resolve|fail|failing|exception|traceback|leak)\b",
            "Diagnose, isolate root cause, and implement robust fix with regression prevention",
        ),
        "feature_create": (
            r"\b(add|create|implement|build|develop|make|write|generate|new|scaffold)\b",
            "Design and implement production-ready capability with complete logic and error handling",
        ),
        "refactor": (
            r"\b(refactor|clean|cleanup|restructure|reorganize|simplify|modularize|modernize|upgrade)\b",
            "Refactor code structure for improved modularity, maintainability, and readability without breaking API contracts",
        ),
        "test_verify": (
            r"\b(test|tests|pytest|verify|check|lint|typecheck|coverage|assert|benchmark|audit)\b",
            "Execute thorough multi-tier verification, assertions, and edge-case testing",
        ),
        "doc_explain": (
            r"\b(document|explain|docs|readme|guide|clarify|comment|architecture)\b",
            "Provide accurate, clear, and comprehensive technical documentation and explanations",
        ),
        "optimize": (
            r"\b(optimize|speed|fast|perf|performance|memory|latency|cache|reduce|benchmark|profile)\b",
            "Profile, identify bottlenecks, and apply efficient optimizations while maintaining correctness",
        ),
        "casual_chat": (
            r"\b(hello|hi|hoi|hey|sup|yo|howdy|greetings|good\s+(?:morning|afternoon|evening)|thanks|thank\s+you|who\s+are\s+you|how\s+are\s+you|what\'?s\s+up|weather|forecast|temperature|joke|jokes|pun|riddle|story|poem)\b",
            "Conversational interaction and pleasantries",
        ),
        "general_qa": (
            r"^(what\s+is|who\s+is|where\s+is|when\s+is|why\s+is|how\s+does|can\s+you\s+explain|tell\s+me\s+about)\b",
            "General knowledge inquiry and question answering",
        ),
    }

    # Specialist domain guidelines
    _DOMAIN_GUIDELINES = {
        "python": [
            "Use modern Python 3.11+ type hints (PEP 484/585/604).",
            "Ensure proper exception handling and defensive error boundaries.",
            "Verify all changes with pytest or syntax compilation.",
            "Preserve existing comments and docstrings unrelated to this change.",
        ],
        "web": [
            "Ensure clean separation of concerns and responsive architecture.",
            "Validate user inputs and handle network latency/failures gracefully.",
            "Avoid hardcoded magic values and untyped configurations.",
        ],
        "database": [
            "Ensure database operations and migrations are strictly idempotent and transactional.",
            "Include proper indexing, constraint checks, and rollback safety.",
            "Prevent SQL injection vulnerabilities via parameterized queries.",
        ],
        "security": [
            "Follow the principle of least privilege and strict input validation.",
            "Eliminate any hardcoded secrets, credentials, or insecure deserialization.",
            "Ensure secure credential handling and error messages that don't leak internals.",
        ],
        "devops": [
            "Ensure cross-platform compatibility (Linux, macOS, Windows).",
            "Verify environment isolation and graceful failure handling.",
            "Provide idempotent provisioning and clear logging outputs.",
        ],
    }

    def __init__(self, root_dir: str | Path | None = None) -> None:
        self.root_dir = Path(root_dir or ".").resolve()

    def enhance(
        self,
        task: str,
        agent_role: str = "Specialist Agent",
        cwd: str | Path | None = None,
        extra_context: str = "",
    ) -> PromptEnhancementResult:
        """Enhance a user task prompt with intent extraction, structure, and constraints."""
        raw_prompt = (task or "").strip()
        if not raw_prompt:
            return PromptEnhancementResult(
                original_prompt="",
                enhanced_prompt="",
                intent_summary="Empty prompt",
                was_modified=False,
                agent_role=agent_role,
            )

        root = Path(cwd or self.root_dir).resolve()
        improvements: list[str] = []

        # 1. Detect primary intent & domain
        intent_category, intent_description = self._classify_intent(raw_prompt)

        # For casual conversation, greetings, weather questions — never inject forced coding boilerplate
        if intent_category == "casual_chat":
            return PromptEnhancementResult(
                original_prompt=raw_prompt,
                enhanced_prompt=raw_prompt,
                intent_summary=f"Conversational inquiry: {raw_prompt}",
                target_scope=[],
                acceptance_criteria=[],
                operational_constraints=[],
                improvements=[],
                was_modified=False,
                agent_role=agent_role,
            )

        improvements.append(f"Structured {intent_category.replace('_', ' ')} intent")

        # 2. Extract potential file / module targets from prompt & workspace
        targets = self._extract_targets(raw_prompt, root)
        if targets:
            improvements.append(f"Identified {len(targets)} workspace targets")

        # 3. Formulate clear objective
        intent_summary = self._formulate_intent_summary(raw_prompt, intent_category, targets)

        # 4. Generate concrete acceptance criteria
        criteria = self._build_acceptance_criteria(raw_prompt, intent_category, targets)
        improvements.append("Defined explicit acceptance criteria")

        # 5. Determine domain constraints
        domain_key = self._infer_domain_key(agent_role, raw_prompt)
        guidelines = list(
            self._DOMAIN_GUIDELINES.get(domain_key, self._DOMAIN_GUIDELINES["python"])
        )
        guidelines.append("Preserve unrelated existing comments and interfaces.")
        guidelines.append("Ensure no placeholders or unfinished mock code remain.")
        improvements.append("Injected domain & verification constraints")

        # 6. Assemble enhanced structured prompt
        enhanced_parts = [
            f"### Primary Objective\n{intent_summary}\n",
            f"### User Intent & Core Request\n{raw_prompt}\n",
        ]

        if targets:
            target_list = "\n".join(f"- `{t}`" for t in targets)
            enhanced_parts.append(f"### Target Scope & Relevant Paths\n{target_list}\n")

        if criteria:
            criteria_list = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(criteria))
            enhanced_parts.append(f"### Acceptance Criteria & Verification\n{criteria_list}\n")

        if guidelines:
            guideline_list = "\n".join(f"- {g}" for g in guidelines)
            enhanced_parts.append(f"### Operational Constraints & Standards\n{guideline_list}\n")

        if extra_context:
            enhanced_parts.append(f"### Additional Task Context\n{extra_context}\n")

        enhanced_text = "\n".join(enhanced_parts).strip()

        result = PromptEnhancementResult(
            original_prompt=raw_prompt,
            enhanced_prompt=enhanced_text,
            intent_summary=intent_summary,
            target_scope=targets,
            acceptance_criteria=criteria,
            operational_constraints=guidelines,
            improvements=improvements,
            was_modified=True,
            agent_role=agent_role,
        )

        # Record to developer telemetry & event tracing
        self._record_telemetry(result)

        return result

    def _classify_intent(self, text: str) -> tuple[str, str]:
        """Classify task into operational intent categories."""
        text_lower = text.lower()
        for cat, (pattern, desc) in self._INTENT_MAP.items():
            if re.search(pattern, text_lower):
                return cat, desc
        return "feature_create", "Execute requested engineering task with precision"

    def _extract_targets(self, text: str, root: Path) -> list[str]:
        """Extract explicit file paths, directories, or symbols mentioned in text."""
        targets: set[str] = set()

        # Matches file-like patterns: src/foo.py, main.py, config.json, etc.
        path_pattern = r"\b(?:[\w\-\./]+(?:\.[\w]{1,10}|/))\b"
        matches = re.findall(path_pattern, text)
        for m in matches:
            cleaned = m.strip().strip("'\"`,:;")
            if cleaned and not cleaned.startswith("http") and not cleaned.startswith("v0."):
                targets.add(cleaned)

        # Check if mentioned names exist in workspace
        try:
            words = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_\-]{2,}\b", text)
            for w in words:
                candidates = list(root.glob(f"**/{w}.*")) + list(root.glob(f"**/{w}"))
                for c in candidates[:3]:
                    if not c.name.startswith("."):
                        try:
                            rel = c.relative_to(root).as_posix()
                            targets.add(rel)
                        except Exception:
                            pass
        except Exception:
            pass

        return sorted(list(targets))[:6]

    def _formulate_intent_summary(self, raw: str, category: str, targets: list[str]) -> str:
        """Formulate a concise high-level intent statement."""
        raw_clean = " ".join(raw.strip().splitlines())
        if len(raw_clean) > 120:
            raw_clean = raw_clean[:117] + "..."

        target_str = f" in {', '.join(targets[:2])}" if targets else ""

        if category == "bug_fix":
            return f"Diagnose and resolve the reported issue{target_str}: {raw_clean}"
        elif category == "refactor":
            return f"Refactor and modernize code architecture{target_str}: {raw_clean}"
        elif category == "test_verify":
            return f"Verify, test, and validate functionality{target_str}: {raw_clean}"
        elif category == "optimize":
            return f"Profile and optimize performance / efficiency{target_str}: {raw_clean}"
        elif category == "doc_explain":
            return f"Document and explain technical specifications{target_str}: {raw_clean}"
        else:
            return f"Implement requested capability{target_str}: {raw_clean}"

    def _build_acceptance_criteria(self, raw: str, category: str, targets: list[str]) -> list[str]:
        """Build explicit acceptance and verification criteria."""
        criteria: list[str] = []

        if category == "bug_fix":
            criteria.append("Identify and isolate the underlying root cause of the failure.")
            criteria.append("Implement a targeted fix that resolves the issue cleanly.")
            criteria.append("Ensure no regressions are introduced into adjacent functionality.")
            criteria.append("Verify fix execution with relevant tests or diagnostics.")
        elif category == "refactor":
            criteria.append("Improve code structure, separation of concerns, and readability.")
            criteria.append("Preserve all existing public APIs, function contracts, and behaviors.")
            criteria.append("Eliminate redundant, dead, or deprecated code paths.")
            criteria.append("Verify all unit tests continue to pass.")
        elif category == "test_verify":
            criteria.append("Execute syntax, linting, and type checks across affected files.")
            criteria.append("Add or run test suites covering both happy path and edge cases.")
            criteria.append("Report clear diagnostic results and remediate any detected flaws.")
        elif category == "optimize":
            criteria.append("Identify computational, memory, or network bottlenecks.")
            criteria.append("Implement efficient algorithmic or caching improvements.")
            criteria.append("Verify that optimized code produces identical expected results.")
        else:
            criteria.append("Implement the complete functionality according to requirements.")
            criteria.append("Ensure robust input validation and defensive error handling.")
            criteria.append("Ensure proper documentation, typings, and tests are provided.")
            criteria.append("Verify execution correctness across target environments.")

        return criteria

    def _infer_domain_key(self, agent_role: str, text: str) -> str:
        """Infer domain category for tailored constraints."""
        combined = f"{agent_role} {text}".lower()
        if any(k in combined for k in ("db", "database", "sql", "postgres", "sqlite", "migration")):
            return "database"
        if any(k in combined for k in ("security", "auth", "token", "secret", "crypto", "jwt")):
            return "security"
        if any(
            k in combined
            for k in ("docker", "deploy", "ssh", "bash", "server", "linux", "cloud", "infra")
        ):
            return "devops"
        if any(
            k in combined for k in ("frontend", "react", "html", "css", "vue", "web", "http", "api")
        ):
            return "web"
        return "python"

    def _record_telemetry(self, res: PromptEnhancementResult) -> None:
        """Record prompt enhancement event to DevTracer and logs."""
        try:
            tracer = get_dev_tracer()
            tracer.record(
                event_type=TraceEventType.PROMPT_ENHANCED,
                source="prompt_enhancer",
                action=f"enhanced_for:{res.agent_role or 'agent'}",
                data={
                    "original_prompt": res.original_prompt,
                    "enhanced_prompt": res.enhanced_prompt,
                    "intent": res.intent_summary,
                    "improvements": res.improvements,
                    "targets": res.target_scope,
                },
            )
        except Exception as exc:
            logger.debug(f"Could not record dev trace event: {exc}")


_ENHANCER_INSTANCE: PromptEnhancer | None = None


def get_prompt_enhancer(root_dir: str | Path | None = None) -> PromptEnhancer:
    """Get or create singleton PromptEnhancer."""
    global _ENHANCER_INSTANCE
    if _ENHANCER_INSTANCE is None:
        _ENHANCER_INSTANCE = PromptEnhancer(root_dir=root_dir)
    return _ENHANCER_INSTANCE


def enhance_prompt(
    task: str,
    agent_role: str = "Specialist Agent",
    cwd: str | Path | None = None,
    extra_context: str = "",
) -> PromptEnhancementResult:
    """Convenience function to enhance a user prompt."""
    enhancer = get_prompt_enhancer(root_dir=cwd)
    return enhancer.enhance(
        task=task,
        agent_role=agent_role,
        cwd=cwd,
        extra_context=extra_context,
    )
