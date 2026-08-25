"""Token-efficient Prompt Enhancer for SAGO.

Analyzes user intent and injects only the minimal context needed for accurate
agent execution. No verbose boilerplate, no directory walking, no 16-rule
anti-hallucination walls. Just the essentials.
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
        tags = " • ".join(self.improvements[:3])
        return (
            f"[bold cyan]✨ Prompt Enhanced[/bold cyan] [dim]({tags})[/dim]\n"
            f"[dim]Intent:[/] [white]{self.intent_summary}[/white]"
        )


class PromptEnhancer:
    """Token-efficient prompt enhancer with smart intent analysis."""

    # Intent categories: (pattern, short description, relevant constraints)
    # Each entry is (compiled_regex_or_str, description, constraints_list)
    _INTENT_PATTERNS: list[tuple[str, str, str, list[str]]] = [
        # Bug fixing
        (
            r"\b(fix|bug|error|broken|crash|crashes|crashing|issue|issues|patch|resolve|fail|failing|failed|exception|traceback|not\s+working|hanging|segfault)\b",
            "bug_fix",
            "Diagnose and fix the reported issue",
            ["Verify fix with tests", "Check for regressions"],
        ),
        # Feature creation
        (
            r"\b(create|add|implement|build|develop|scaffold|write|make)\s+(?:a\s+|an\s+|the\s+)?(?:new\s+)?(?:script|function|class|module|file|tool|app|feature|endpoint|api|command)\b",
            "feature_create",
            "Implement the requested feature",
            ["Include error handling", "Add tests if applicable"],
        ),
        # Refactoring
        (
            r"\b(refactor|restructure|reorganize|clean\s+up|simplify|modernize|upgrade|rename|move)\b",
            "refactor",
            "Refactor code while preserving behavior",
            ["Preserve public API", "Verify tests still pass"],
        ),
        # Testing
        (
            r"\b(test|tests|pytest|unittest|verify|check|lint|typecheck|coverage|assert|audit)\b",
            "test_verify",
            "Run tests and verification",
            ["Report actual results", "Don't claim tests pass without running them"],
        ),
        # Optimization
        (
            r"\b(optimize|performance|speed|fast|slow|cache|latency|benchmark|memory|bottleneck)\b",
            "optimize",
            "Optimize performance",
            ["Measure before/after", "Don't claim improvement without evidence"],
        ),
        # Documentation
        (
            r"\b(document|explain|docs|readme|guide|comment|clarify|how\s+does)\b",
            "doc_explain",
            "Document or explain the code",
            ["Reference actual code", "Don't fabricate function names"],
        ),
        # DevOps
        (
            r"\b(docker|k8s|deploy|ci/cd|pipeline|Dockerfile|docker-compose|nginx|systemd)\b",
            "devops",
            "Configure deployment and infrastructure",
            ["Ensure idempotency", "Test configuration"],
        ),
        # Exploration
        (
            r"\b(what\s+is|where\s+is|show\s+me|list|find|search|look\s+for|explore|overview|structure)\b",
            "explore",
            "Explore and analyze the codebase",
            ["Use tools to verify claims", "Report actual findings"],
        ),
        # Git operations
        (
            r"\b(commit|push|pull|merge|branch|stash|revert|reset|diff|log|blame)\b",
            "git",
            "Perform git operation",
            ["Confirm before destructive ops"],
        ),
        # Dependency management
        (
            r"\b(install|upgrade|downgrade|remove|add)\s+(?:the\s+)?(?:package|dependency|library|module)\b",
            "dependency",
            "Manage project dependencies",
            ["Check compatibility", "Update lockfiles"],
        ),
        # Casual / greeting
        (
            r"^(?:hi|hello|hey|yo|sup|howdy|greetings|good\s+(?:morning|afternoon|evening)|thanks|thank\s+you|who\s+are\s+you|what\s+can\s+you\s+do|how\s+are\s+you|what'?s\s+up)\b|"
            r"(?:what|wehta|wat|wht)\s+(?:can|do)\s+(?:you|yiu|u)\s+(?:do|help|perform|show|tell)|"
            r"\b(?:what\s+are\s+your\s+(?:capabilities|skills|tools|features)|who\s+are\s+you|what\s+is\s+sago|what\s+can\s+i\s+ask|what\s+can\s+you\s+do)\b",
            "casual",
            "Conversational",
            [],
        ),
        # General question
        (
            r"^(what|who|where|when|why|how|can\s+you|could\s+you|would\s+you|is\s+it|are\s+there|do\s+you|should\s+I)\b",
            "question",
            "Answer the user's question",
            ["Be concise", "Cite sources if applicable"],
        ),
    ]

    # Core anti-hallucination rules — compact but covering fabrication, verification, uncertainty
    _CORE_RULES = [
        "Verify claims with tools — don't say 'the code does X' without reading it.",
        "If unsure, say so. Don't fabricate file names, function names, or APIs.",
        "Never claim tests pass or a file was created without actually running tests / calling write_file/edit_file.",
        "Report only what tools returned; state uncertainty rather than guessing structure or quality.",
    ]

    # Domain-specific constraints (only injected when relevant)
    _DOMAIN_CONSTRAINTS = {
        "python": ["Use type hints", "Handle exceptions", "Verify with pytest"],
        "web": ["Validate inputs", "Handle errors gracefully", "No hardcoded secrets"],
        "database": ["Use parameterized queries", "Ensure migrations are idempotent"],
        "security": ["No hardcoded credentials", "Validate all inputs"],
        "devops": ["Ensure idempotency", "Test configuration"],
        "java": ["Use proper exception handling", "Follow SOLID principles"],
        "rust": ["Handle Result types", "Avoid unwrap() in production code"],
        "go": ["Handle errors explicitly", "Use context for cancellation"],
    }

    # Simple query signals — skip enhancement for these
    _SKIP_PATTERNS = [
        r"^(?:hi|hello|hey|yo|sup|howdy|greetings|bye|hoi|heyy|heya)\b",
        r"^(?:thanks|thank\s+you|thx|ty|cheers)\b",
        r"^(?:yes|no|ok|okay|sure|nope|yep|yeah|nah)\b",
        r"^(?:good|bad|great|nice|cool|awesome)\b",
        r"^\w+\??$",  # Single word questions
        r"^(?:what\s+time|what\s+date|what\s+day)\b",
        r"(?:what|wehta|wat|wht)\s+(?:can|do)\s+(?:you|yiu|u)\s+(?:do|help|perform)",
        r"(?:what|who)\s+are\s+your\s+(?:capabilities|skills|tools|features)",
        r"who\s+are\s+you",
        r"what\s+is\s+sago",
        r"what\s+can\s+(?:i|you)\s+(?:ask|do)",
        r"how\s+are\s+you",
        r"what'?s\s+up",
        r"(?:tell\s+me\s+a\s+joke|jokes?|pun|riddle|story|poem)",
        r"(?:weather|forecast|temperature)",
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
        """Enhance a user prompt with minimal, targeted additions."""
        raw = (task or "").strip()
        if not raw:
            return PromptEnhancementResult(
                original_prompt="",
                enhanced_prompt="",
                intent_summary="Empty prompt",
                was_modified=False,
                agent_role=agent_role,
            )

        # Skip enhancement for simple/greeting queries
        if self._is_simple_query(raw):
            return PromptEnhancementResult(
                original_prompt=raw,
                enhanced_prompt=raw,
                intent_summary=raw,
                was_modified=False,
                agent_role=agent_role,
            )

        # Classify intent
        intent_key, intent_desc, constraints = self._classify_intent(raw)

        # Skip enhancement for casual chat
        if intent_key == "casual":
            return PromptEnhancementResult(
                original_prompt=raw,
                enhanced_prompt=raw,
                intent_summary=intent_desc,
                was_modified=False,
                agent_role=agent_role,
            )

        # Extract file targets (fast regex only, no directory walking)
        targets = self._extract_file_refs(raw)

        # Detect domain for targeted constraints
        domain = self._detect_domain(agent_role, raw)
        domain_rules = self._DOMAIN_CONSTRAINTS.get(domain, [])

        # Build minimal enhanced prompt
        enhanced = self._build_prompt(
            raw, intent_desc, targets, constraints, domain_rules, extra_context
        )

        # Build acceptance criteria (just the task-relevant ones)
        criteria = self._build_criteria(intent_key, raw)

        improvements = []
        if intent_key != "question":
            improvements.append(f"{intent_key.replace('_', ' ')} intent")
        if targets:
            improvements.append(f"{len(targets)} file ref(s)")
        if domain_rules:
            improvements.append(f"{domain} domain")
        if extra_context:
            improvements.append("extra context")

        result = PromptEnhancementResult(
            original_prompt=raw,
            enhanced_prompt=enhanced,
            intent_summary=intent_desc,
            target_scope=targets,
            acceptance_criteria=criteria,
            operational_constraints=constraints + domain_rules,
            improvements=improvements,
            was_modified=True,
            agent_role=agent_role,
        )

        self._record_telemetry(result)
        return result

    def enhance_with_llm(
        self,
        task: str,
        agent_role: str = "Specialist Agent",
        cwd: str | Path | None = None,
        extra_context: str = "",
        client: Any = None,
        model: str = "",
    ) -> PromptEnhancementResult:
        """LLM-enhanced prompt improvement. Falls back to regex on failure."""
        raw = (task or "").strip()
        if not raw:
            return PromptEnhancementResult(
                original_prompt="",
                enhanced_prompt="",
                intent_summary="Empty prompt",
                was_modified=False,
                agent_role=agent_role,
            )

        # Simple queries: skip LLM call entirely
        if self._is_simple_query(raw):
            return self.enhance(
                task=task, agent_role=agent_role, cwd=cwd, extra_context=extra_context
            )

        targets = self._extract_file_refs(raw)

        # Compact LLM prompt — much smaller than before
        llm_prompt = f"""Analyze this task and return JSON with:
- "intent": 1-sentence summary (max 60 chars)
- "criteria": list of 2-3 success criteria
- "enhanced": clear task description preserving exact user intent

Rules: No fabrication. If vague, say what's unclear. Output ONLY JSON.

Agent: {agent_role}
Files: {", ".join(targets[:3]) if targets else "none"}

Task: {raw[:1500]}"""

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": llm_prompt}],
                max_tokens=300,
                temperature=0.1,
                stream=False,
            )
            llm_text = response.choices[0].message.content or ""

            # Extract JSON
            json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", llm_text, re.DOTALL)
            if json_match:
                llm_text = json_match.group(1).strip()
            else:
                json_match = re.search(r"\{.*\}", llm_text, re.DOTALL)
                if json_match:
                    llm_text = json_match.group(0)

            import json as _json

            llm_data = _json.loads(llm_text)

            llm_intent = llm_data.get("intent", "")
            llm_criteria = llm_data.get("criteria", [])
            llm_enhanced = llm_data.get("enhanced", "")

            if llm_enhanced and len(llm_enhanced) > 10:
                # Use LLM result but keep constraints minimal
                intent_key, intent_desc, constraints = self._classify_intent(raw)
                domain = self._detect_domain(agent_role, raw)
                domain_rules = self._DOMAIN_CONSTRAINTS.get(domain, [])

                enhanced_parts = [llm_enhanced]
                if targets:
                    enhanced_parts.append(f"\nFiles: {', '.join(targets)}")
                if llm_criteria:
                    criteria_text = "; ".join(llm_criteria)
                    enhanced_parts.append(f"\nCriteria: {criteria_text}")
                if domain_rules:
                    enhanced_parts.append(f"\nDomain: {', '.join(domain_rules[:2])}")

                enhanced = "\n".join(enhanced_parts)

                result = PromptEnhancementResult(
                    original_prompt=raw,
                    enhanced_prompt=enhanced,
                    intent_summary=llm_intent or intent_desc,
                    target_scope=targets,
                    acceptance_criteria=llm_criteria or self._build_criteria(intent_key, raw),
                    operational_constraints=constraints + domain_rules,
                    improvements=["LLM-enhanced", f"{intent_key.replace('_', ' ')} intent"],
                    was_modified=True,
                    agent_role=agent_role,
                )
                self._record_telemetry(result)
                return result

        except Exception as e:
            logger.debug("LLM enhancement failed: %s", e)

        # Fallback to regex-based enhancement
        return self.enhance(task=task, agent_role=agent_role, cwd=cwd, extra_context=extra_context)

    def _is_simple_query(self, text: str) -> bool:
        """Check if query is too simple to warrant enhancement."""
        text_lower = text.lower().strip()
        word_count = len(text_lower.split())

        # Very short single word
        if word_count <= 1:
            return True

        # If query has code-related intent, never skip enhancement
        code_intents = (
            "fix",
            "bug",
            "error",
            "create",
            "add",
            "build",
            "implement",
            "refactor",
            "deploy",
            "install",
            "run",
            "test",
            "check",
            "optimize",
            "document",
            "explain",
            "find",
            "search",
            "show",
            "list",
            "set",
            "configure",
            "update",
            "delete",
            "remove",
            "rename",
            "move",
            "copy",
            "commit",
            "push",
            "refactor",
            "scaffold",
        )
        words = text_lower.split()
        if any(w in code_intents for w in words):
            return False

        # Match simple patterns (greetings, acknowledgments)
        for pattern in self._SKIP_PATTERNS:
            if re.search(pattern, text_lower):
                return True

        # Short non-action queries (2-3 words) are simple
        if word_count <= 3:
            return True

        return False

    def _classify_intent(self, text: str) -> tuple[str, str, list[str]]:
        """Classify intent and return (key, description, constraints)."""
        text_lower = text.lower()

        for pattern, key, desc, constraints in self._INTENT_PATTERNS:
            if re.search(pattern, text_lower):
                return key, desc, constraints

        # Fallback: generic implementation task
        return "feature", "Implement the requested task", []

    def _detect_domain(self, agent_role: str, text: str) -> str:
        """Detect domain from agent role and text content."""
        combined = f"{agent_role} {text}".lower()

        if any(k in combined for k in ("python", "pytest", "django", "flask", "fastapi")):
            return "python"
        if any(k in combined for k in ("java", "spring", "maven", "gradle")):
            return "java"
        if any(k in combined for k in ("rust", "cargo", "clippy")):
            return "rust"
        if any(k in combined for k in ("go", "golang")):
            return "go"
        if any(
            k in combined for k in ("react", "vue", "angular", "html", "css", "frontend", "web")
        ):
            return "web"
        if any(k in combined for k in ("sql", "postgres", "sqlite", "database", "migration")):
            return "database"
        if any(k in combined for k in ("docker", "k8s", "deploy", "ci/cd", "nginx")):
            return "devops"
        if any(k in combined for k in ("security", "auth", "token", "jwt", "crypto")):
            return "security"
        return "python"  # default

    def _extract_file_refs(self, text: str) -> list[str]:
        """Extract file references from text using fast regex. No directory walking."""
        # Match common file patterns: path/to/file.ext
        file_pattern = r"(?:[\w\-./]+\.(?:py|js|ts|jsx|tsx|go|rs|java|kt|rb|php|c|cpp|h|hpp|cs|swift|scala|sh|bash|yml|yaml|json|toml|cfg|ini|env|md|txt|sql|html|css|scss|less))"
        matches = re.findall(file_pattern, text)

        # Deduplicate and clean
        seen = set()
        targets = []
        for m in matches:
            cleaned = m.strip("'\"`,:;")
            if cleaned and cleaned not in seen and not cleaned.startswith("http"):
                seen.add(cleaned)
                targets.append(cleaned)

        return targets[:5]

    def _build_prompt(
        self,
        raw: str,
        intent_desc: str,
        targets: list[str],
        constraints: list[str],
        domain_rules: list[str],
        extra_context: str,
    ) -> str:
        """Build minimal enhanced prompt. No verbose markdown headers."""
        parts = [raw]

        if targets:
            parts.append(f"\nFiles: {', '.join(targets)}")

        if constraints:
            parts.append(f"\nRequirements: {'; '.join(constraints)}")

        if domain_rules:
            parts.append(f"\nStandards: {'; '.join(domain_rules[:3])}")

        if extra_context:
            parts.append(f"\nContext: {extra_context}")

        # Add core anti-hallucination rules (just 2)
        parts.append(f"\nRules: {'; '.join(self._CORE_RULES)}")

        return "\n".join(parts)

    def _build_criteria(self, intent_key: str, raw: str) -> list[str]:
        """Build minimal, task-relevant acceptance criteria."""
        criteria_map = {
            "bug_fix": ["Root cause identified", "Fix verified with tests", "No regressions"],
            "feature_create": ["Feature works as specified", "Error handling included"],
            "refactor": ["Behavior preserved", "Tests pass", "Code cleaner"],
            "test_verify": ["Tests run and results reported", "Issues found and fixed"],
            "optimize": ["Performance measured before/after", "Correctness verified"],
            "doc_explain": ["Documentation references actual code", "Explanation is accurate"],
            "devops": ["Config is idempotent", "Deployment tested"],
            "explore": ["Findings based on actual file reads", "Structure accurately described"],
            "git": ["Operation confirmed before execution", "No data loss"],
            "dependency": ["Compatibility checked", "Lockfile updated"],
            "question": ["Answer is accurate and concise"],
            "feature": ["Implementation complete", "Error handling included"],
        }
        return criteria_map.get(intent_key, ["Task completed successfully"])

    def _record_telemetry(self, res: PromptEnhancementResult) -> None:
        """Record enhancement event."""
        try:
            tracer = get_dev_tracer()
            tracer.record(
                event_type=TraceEventType.PROMPT_ENHANCED,
                source="prompt_enhancer",
                action=f"enhanced_for:{res.agent_role or 'agent'}",
                data={
                    "original_prompt": res.original_prompt[:200],
                    "enhanced_prompt": res.enhanced_prompt[:200],
                    "intent": res.intent_summary,
                    "improvements": res.improvements,
                },
            )
        except Exception:
            pass


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
    llm_client: Any = None,
    llm_model: str = "",
) -> PromptEnhancementResult:
    """Convenience function to enhance a user prompt."""
    enhancer = get_prompt_enhancer(root_dir=cwd)

    if llm_client and llm_model:
        try:
            return enhancer.enhance_with_llm(
                task=task,
                agent_role=agent_role,
                cwd=cwd,
                extra_context=extra_context,
                client=llm_client,
                model=llm_model,
            )
        except Exception as e:
            logger.debug("LLM enhancement failed, falling back to regex: %s", e)

    return enhancer.enhance(
        task=task,
        agent_role=agent_role,
        cwd=cwd,
        extra_context=extra_context,
    )


def generate_session_title(messages: list[dict[str, Any]] | str) -> str:
    """Generate a clean one-liner title for a session."""
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
        else:
            title = first_user_text
    except Exception:
        title = first_user_text

    # Strip filler phrasing
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
