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
            r"\b(fix|bug|bugs|error|errors|broken|crash|crashes|issue|issues|patch|resolve|fail|failing|failed|exception|traceback|leak|why\s+(?:is\s+this\s+not\s+working|is\s+it\s+not\s+working|does\s+this\s+fail|am\s+i\s+getting|is\s+it\s+broken)|not\s+working|not\s+starting|hanging)\b",
            "Diagnose, isolate root cause, and implement robust fix with regression prevention",
        ),
        "explore_arch": (
            r"\b(projects?|project\s+structure|codebase|architecture|topology|overview|modules?|layout|where\s+is\s+(?:the\s+config|[\w\-]+)|what\s+projects\s+are\s+in\s+here)\b",
            "Explore repository architecture, module topology, and components",
        ),
        "optimize": (
            r"\b(optimize|optimization|speed|fast|perf|performance|memory|latency|cache|reduce|benchmark|profile|slow|bottleneck|make\s+it\s+faster)\b",
            "Profile, identify bottlenecks, and apply efficient optimizations while maintaining correctness",
        ),
        "refactor": (
            r"\b(clean\s+(?:this\s+up|up|the\s+code)|make\s+this\s+cleaner|tidy\s+up|refactor|restructure|reorganize|simplify|modularize|modernize|upgrade)\b",
            "Refactor code structure for improved modularity, maintainability, and readability without breaking API contracts",
        ),
        "test_verify": (
            r"\b(test|tests|pytest|unittest|verify|check|lint|typecheck|coverage|assert|benchmark|audit|why\s+is\s+(?:test|pytest)\s+failing)\b",
            "Execute thorough multi-tier verification, assertions, and edge-case testing",
        ),
        "devops": (
            r"\b(docker|k8s|kubernetes|dockerfile|docker-compose|deploy|deployment|ci/cd|pipeline|how\s+(?:do\s+i\s+run\s+this|to\s+run\s+this|to\s+start|to\s+deploy))\b",
            "Configure environment, containerization, and infrastructure deployment",
        ),
        "feature_create": (
            r"\b(add|create|implement|build|develop|scaffold|write\s+(?:code|a\s+script|tests?|a\s+function|a\s+class)|make\s+(?:a\s+script|a\s+function|a\s+class|an\s+app|a\s+tool))\b",
            "Design and implement production-ready capability with complete logic and error handling",
        ),
        "doc_explain": (
            r"\b(document|explain|docs|readme|guide|clarify|comment)\b",
            "Provide accurate, clear, and comprehensive technical documentation and explanations",
        ),
        "casual_chat": (
            r"\b(hello|hellos|helloo|hi|hii|hiii|hoi|heyy|heyyy|hey|heya|sup|yo|yoo|howdy|greetings|good\s+(?:morning|afternoon|evening|day)|thanks|thank\s+you|who\s+are\s+you|how\s+are\s+you|what\'?s\s+up|weather|forecast|temperature|joke|jokes|pun|riddle|story|poem)\b|"
            r"(?:what|wehta|wat|wht)\s+(?:can|do)\s+(?:you|yiu|u)\s+(?:do|help|perform|show|tell)|"
            r"\b(what\s+are\s+your\s+(?:capabilities|skills|tools|features|agents)|who\s+are\s+you|what\s+is\s+sago|help\s+me\s+understand\s+what\s+you\s+can\s+do|what\s+can\s+i\s+ask\s+you|what\s+can\s+you\s+do)\b",
            "Conversational interaction, pleasantries, or capability inquiry",
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

    # Anti-hallucination constraints injected into all enhanced prompts
    _ANTI_HALLUCINATION_CONSTRAINTS = [
        "NEVER claim to have read a file without actually calling read_file tool first.",
        "NEVER claim tests pass without actually running them via execute_shell tool.",
        "NEVER claim a file was created or modified without calling write_file or edit_file.",
        "If uncertain about code contents, state uncertainty rather than guessing.",
        "Always verify tool results before reporting them as facts.",
        "Cross-reference your claims against actual tool call history.",
        "NEVER claim code is 'production-ready', 'fully tested', 'complete', or 'works perfectly' without tool evidence.",
        "NEVER fabricate function names, class names, or API methods that don't exist in the codebase.",
        "If you haven't searched the codebase, don't claim something 'doesn't exist' or 'isn't used'.",
        "NEVER claim 'no errors' or 'all checks pass' without actually running linters/tests.",
    ]

    # Overthinking prevention: complexity signals that indicate simple queries
    _SIMPLE_QUERY_SIGNALS = [
        r"^(?:hi|hello|hey|yo|sup|howdy|greetings)\b",
        r"^(?:thanks|thank\s+you|thx|ty|cheers)\b",
        r"^(?:what\s+is|who\s+is|what\s+are)\s+\d+",
        r"^(?:can\s+you\s+)?(?:explain|describe|what\s+does)\s+\w+\s+(?:do|mean)\b",
        r"^(?:how\s+(?:do|can|to))\s+(?:i|we)\s+\w+",
        r"^(?:where|when|why|how)\s+(?:is|are|was|were|do|does|did)\b",
        r"^(?:yes|no|ok|okay|sure|nope|yep|yeah|nah)\b",
        r"^(?:good|bad|great|nice|cool|awesome|excellent|terrible)\b",
        r"^(?:what|which)\s+(?:file|function|class|method|variable)\s+(?:is|are|was)\b",
        r"^\w+\??$",  # Single word questions
    ]

    # Complexity signals that indicate multi-step tasks
    _COMPLEX_QUERY_SIGNALS = [
        r"\b(?:refactor|redesign|restructure|rewrite)\s+(?:the\s+)?(?:entire|whole|full)\b",
        r"\b(?:implement|build|create|add)\s+(?:a\s+)?(?:complete|full|entire|comprehensive)\b",
        r"\b(?:migrate|upgrade|overhaul)\s+(?:from|to)\b",
        r"\b(?:all|every|each)\s+(?:file|module|component|service)\b",
        r"\b(?:architecture|system\s+design|infrastructure)\b",
        r"\b(?:multi[\s-]step|step[\s-]by[\s-]step|phased)\b",
        r"\b(?:security|performance|scalability)\s+(?:audit|review|analysis)\b",
    ]

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

        # 2. Assess complexity to prevent overthinking on simple queries
        complexity = self._assess_complexity(raw_prompt)
        if complexity == "simple":
            # For simple queries, return minimal enhancement to avoid overthinking
            improvements.append("Simple query detected — minimal enhancement")
            return PromptEnhancementResult(
                original_prompt=raw_prompt,
                enhanced_prompt=raw_prompt,
                intent_summary=f"Simple {intent_category.replace('_', ' ')}: {raw_prompt}",
                target_scope=[],
                acceptance_criteria=[],
                operational_constraints=[],
                improvements=improvements,
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

        # 6. Inject anti-hallucination constraints
        guidelines.extend(self._ANTI_HALLUCINATION_CONSTRAINTS)
        improvements.append("Injected anti-hallucination safeguards")

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

    def _assess_complexity(self, text: str) -> str:
        """Assess query complexity to prevent overthinking on simple queries.

        Returns 'simple', 'medium', or 'complex'.
        Only returns 'simple' for truly trivial queries (greetings, single words,
        basic questions) — NOT for code-related tasks.
        """
        text_lower = text.lower().strip()
        word_count = len(text_lower.split())

        # Check for complex query signals FIRST (don't skip these)
        complex_signals = 0
        for pattern in self._COMPLEX_QUERY_SIGNALS:
            if re.search(pattern, text_lower):
                complex_signals += 1

        if complex_signals >= 2 or word_count > 50:
            return "complex"
        elif complex_signals >= 1 or word_count > 25:
            return "medium"

        # Only return 'simple' for genuinely trivial, non-code queries
        # Check for code-related words — if present, never skip enhancement
        code_indicators = (
            "file",
            "code",
            "function",
            "class",
            "method",
            "module",
            "import",
            "fix",
            "bug",
            "error",
            "test",
            "refactor",
            "implement",
            "create",
            "delete",
            "add",
            "remove",
            "update",
            "change",
            "rename",
            ".py",
            ".js",
            ".ts",
            ".go",
            ".rs",
            ".java",
        )
        has_code_intent = any(word in text_lower for word in code_indicators)

        if has_code_intent:
            # Code tasks are at least medium complexity
            return "medium"

        # Non-code: check for simple query patterns
        simple_patterns = (
            r"^(?:hi|hello|hey|yo|sup|howdy|greetings|bye|goodbye)\b",
            r"^(?:thanks|thank\s+you|thx|ty|cheers)\b",
            r"^(?:yes|no|ok|okay|sure|nope|yep|yeah|nah)\b",
            r"^(?:good|bad|great|nice|cool|awesome|excellent|terrible)\b",
            r"^(?:what\s+is\s+\d+[\s+\-*/\d]*)\b",
            r"^(?:what\s+time|what\s+date|what\s+day)\b",
            r"^\w+\??$",
        )
        is_simple = any(re.search(p, text_lower) for p in simple_patterns)

        if is_simple and word_count <= 8:
            return "simple"
        elif word_count <= 5:
            return "simple"
        else:
            return "medium"

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
        elif category == "explore_arch":
            return f"Explore and analyze codebase architecture and layout{target_str}: {raw_clean}"
        elif category == "devops":
            return (
                f"Configure environment, containerization, or deployment{target_str}: {raw_clean}"
            )
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
        elif category == "explore_arch":
            criteria.append(
                "Analyze directory structure, project dependencies, and module relationships."
            )
            criteria.append("Identify core components, entrypoints, and communication flows.")
            criteria.append("Provide a clear, structured architecture summary.")
        elif category == "devops":
            criteria.append(
                "Verify environment isolation, configuration files, and script reliability."
            )
            criteria.append("Ensure deployment/dockerization scripts execute idempotently.")
            criteria.append("Provide clear execution steps and verification checks.")
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

        # Universal anti-hallucination criteria for all task types
        criteria.append(
            "NEVER claim verification without running actual tools (tests, lints, syntax checks)."
        )
        criteria.append(
            "Report only what was actually observed via tools — state uncertainty when unsure."
        )

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


def generate_session_title(messages: list[dict[str, Any]] | str) -> str:
    """Generate a clean, high-impact one-liner title for a session based on user intent."""
    first_user_text = ""
    if isinstance(messages, str):
        first_user_text = messages.strip()
    elif isinstance(messages, list):
        for m in messages:
            if m.get("role") == "user" and m.get("content"):
                first_user_text = str(m.get("content")).strip()
                break

    if not first_user_text:
        return "Interactive Session"

    try:
        enh = enhance_prompt(first_user_text)
        if enh.intent_summary and not enh.intent_summary.startswith("Empty"):
            title = enh.intent_summary
            title = re.sub(
                r"^(?:Conversational inquiry:\s*|Diagnose and resolve the reported issue(?:\s+in\s+[^:]+)?:\s*|Explore and analyze codebase architecture and layout(?:\s+in\s+[^:]+)?:\s*|Implement requested capability(?:\s+in\s+[^:]+)?:\s*|Refactor and modernize code architecture(?:\s+in\s+[^:]+)?:\s*|Profile and optimize performance\s*/\s*efficiency(?:\s+in\s+[^:]+)?:\s*)",
                "",
                title,
                flags=re.IGNORECASE,
            ).strip()
        else:
            title = first_user_text
    except Exception:
        title = first_user_text

    # Strip filler conversational phrasing
    title = re.sub(
        r"^(?:please\s+|can\s+you\s+|could\s+you\s+|i\s+need\s+you\s+to\s+|help\s+me\s+)",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()
    title = " ".join(title.splitlines())
    if len(title) > 60:
        title = title[:57] + "..."

    title = title.strip().rstrip(".:;!?")
    if title:
        title = title[0].upper() + title[1:]
    return title or "Interactive Session"
