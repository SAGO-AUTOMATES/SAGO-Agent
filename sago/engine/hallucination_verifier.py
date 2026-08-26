"""Shared Hallucination Verification Module for Sago.

Provides a unified verification pipeline that can be used by all execution paths
(simple_executor, orchestrator, production, streaming) to detect and prevent
hallucinations in LLM responses.

Architecture:
    ResponseVerifier.verify() is the main entry point. It runs:
    1. Fabrication phrase detection (regex-based)
    2. Claim vs tool-history cross-referencing
    3. Hedging/subtle claim detection
    4. Code block syntax validation (multi-language)
    5. File path existence verification
    6. Import/module validation
    7. External syntax verification (py_compile, gofmt, rustfmt, node)
    8. Tool result integrity checking (plugin tamper detection)
    9. Response sanitization (strip unverified claims)
"""

from __future__ import annotations

import ast
import hashlib
import logging
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("sago.engine.hallucination_verifier")


# ---- Constants ----
_MIN_CODE_LENGTH = 20
_SYNTAX_CHECK_TIMEOUT = 30
_ERROR_MESSAGE_MAX_LEN = 200
_CONFIDENCE_THRESHOLD = 50
_CHAT_SKIP_CONFIDENCE = 85
_HISTORY_MAX_SIZE = 50


@dataclass
class VerificationResult:
    """Result of hallucination verification."""

    original_content: str
    cleaned_content: str
    issues: list[str] = field(default_factory=list)
    code_issues: list[str] = field(default_factory=list)
    claim_issues: list[str] = field(default_factory=list)
    external_issues: list[str] = field(default_factory=list)
    hedging_issues: list[str] = field(default_factory=list)
    integrity_issues: list[str] = field(default_factory=list)
    confidence: int = 100
    has_hallucinations: bool = False
    sanitized: bool = False

    @property
    def all_issues(self) -> list[str]:
        return (
            self.issues
            + self.code_issues
            + self.claim_issues
            + self.external_issues
            + self.hedging_issues
            + self.integrity_issues
        )


# ---- Fabrication Phrases (comprehensive) ----

_FABRICATION_PHRASES = [
    # Verification claims
    r"\bi(?:'ve| have)\s+(?:verified|confirmed|checked|validated|tested|confirmed that|run)\b",
    r"\bverified\s+(?:that\s+)?(?:the\s+)?(?:code|fix|change|implementation)\b",
    r"\bconfirmed\s+(?:that\s+)?(?:the\s+)?(?:code|fix|change|implementation)\b",
    r"\bchecked\s+(?:that\s+)?(?:the\s+)?(?:code|fix|change|implementation)\b",
    # Test claims
    r"\bthe\s+tests?\s+(?:pass|passes|passed|are\s+passing|all\s+pass)\b",
    r"\b(?:all|every|each)\s+tests?\s+(?:pass|passes|passed|are\s+passing)\b",
    r"\b(?:no|zero)\s+test\s+failures?\b",
    r"\b(?:every|all)\s+assertions?\s+pass\b",
    r"\btest\s+(?:suite|coverage)\s+(?:is|shows?|indicates?)\b",
    r"\b\d+\s+(?:out\s+of|\/)\s+\d+\s+tests?\s+pass\b",
    # Lint/type check claims
    r"\b(?:lint|type\s*check|static\s+analysis)\s+(?:passes?|passes|clean|clear|no\s+errors?)\b",
    r"\bno\s+(?:lint|linting|type)\s+errors?\b",
    r"\bcode\s+(?:passes?|is)\s+(?:linting|type\s+checking|formatting)\b",
    # Code quality claims
    r"\bthe\s+code\s+(?:compiles?|builds?|works?|runs?)\b",
    r"\bthe\s+code\s+(?:is|follows?)\s+(?:clean|proper|correct|valid)\b",
    r"\bcode\s+(?:is|follows?)\s+PEP\s+\d+\b",
    r"\bno\s+(?:syntax|runtime|type)\s+errors?\b",
    # Fix claims
    r"\bi(?:'ve| have)\s+(?:fixed|resolved|patched|corrected|addressed)\b",
    r"\bthis\s+(?:fix|change|patch|modification)\s+(?:resolves?|fixes?|solves?|addresses?)\b",
    r"\bthe\s+(?:fix|issue|bug|error)\s+(?:is|has\s+been)\s+(?:resolved|fixed|addressed)\b",
    r"\bnow\s+(?:it|the\s+code|the\s+system)\s+(?:works?|functions?|runs?)\b",
    # Success/completion claims
    r"\bno\s+(?:errors?|issues?|problems?|bugs?)\s+(?:remain|left|found|detected)\b",
    r"\b(?:everything|it)\s+(?:works?|is\s+working|should\s+work|looks?\s+good)\b",
    r"\b(?:i'm|I'm)\s+(?:confident|certain|sure)\s+(?:that\s+)?(?:this|it)\b",
    r"\bcorrectly\s+handles?\b",
    r"\bproperly\s+(?:implements?|handles?|manages?|processes?)\b",
    r"\bfully\s+(?:functional|implemented|working|tested)\b",
    r"\bcomprehensive\s+(?:test|coverage|solution)\b",
    r"\bwell[\s-]structured\b",
    r"\bproduction[\s-]ready\b",
    r"\bcompletely\s+(?:fixes?|resolves?|handles?)\b",
    r"\bshould\s+(?:now|work|function|run)\s+(?:correctly|properly|as\s+expected)\b",
    # Structural/architectural claims without tools
    r"\bthe\s+(?:codebase|project|repository|repo)\s+(?:has|contains?|includes?)\s+\d+\b",
    r"\bthere\s+(?:are|is)\s+\d+\s+(?:files?|classes?|functions?|methods?|modules?)\b",
    r"\bthe\s+(?:project|codebase)\s+(?:uses?|relies?\s+on|is\s+built\s+(?:with|on))\b",
    r"\bbased\s+on\s+(?:my\s+)?(?:analysis|review|inspection)\s+of\b",
    r"\bafter\s+(?:analyzing|reviewing|inspecting|examining)\b",
    r"\b(?:looking|looking)\s+at\s+the\s+(?:code|implementation|structure)\b",
    r"\bfrom\s+what\s+(?:i|we)\s+(?:can\s+see|see|found)\b",
    # Coverage/quality metrics without measurement
    r"\btest\s+coverage\s+(?:is|shows?|indicates?)\s+\d+%\b",
    r"\b\d+%\s+test\s+coverage\b",
    r"\bno\s+security\s+(?:vulnerabilities?|issues?|risks?)\b",
    r"\b(?:all|every)\s+(?:edge\s+cases?|corner\s+cases?)\s+(?:are|is)\s+handled\b",
    # Recommendation claims without evidence
    r"\bi\s+(?:recommend|suggest|advise)\s+(?:that\s+)?(?:you|we)\s+(?:should|could|can)\b",
    r"\bthe\s+(?:best|optimal|recommended)\s+(?:approach|solution|way)\s+(?:is|would\s+be)\b",
    r"\bthis\s+(?:is|will\s+be)\s+(?:more|less|better|worse|faster|slower)\s+efficient\b",
]

# Inline fabrication phrases (for no-tool-call detection)
_INLINE_FABRICATION_PHRASES = [
    # File content claims
    "the file contains",
    "the contents are",
    "i read the file",
    "the file has",
    "i can see that",
    "looking at the file",
    "the code shows",
    "i opened the file",
    "the file shows",
    "after reading the file",
    "examining the file",
    "reviewing the file",
    "inspecting the file",
    "checking the file",
    "the file at",
    "opening the file",
    # File creation/modification claims
    "successfully created",
    "i saved the file",
    "the file was created",
    "i have created",
    "i've created",
    "done! the file",
    "i've updated",
    "i have updated",
    "i've added",
    "i have added",
    "i've removed",
    "i have removed",
    "i've deleted",
    "i have deleted",
    "i've modified",
    "i have modified",
    "the updated file",
    "the modified file",
    "i've written",
    "i have written",
    "i went ahead and",
    "i've gone ahead",
    "just finished",
    "i've already",
    # Code content claims
    "the code below",
    "here's the code",
    "here is the code",
    "as shown in",
    "as we can see",
    "based on the file",
    "after reviewing",
    "the function returns",
    "the class implements",
    "the module provides",
    "the implementation uses",
    "the logic handles",
    # Fix/analysis claims without tools
    "the fix involves",
    "the issue is",
    "the problem is",
    "the solution is",
    "here's the fix",
    "here is the fix",
    "the error occurs because",
    "the bug is in",
    "fixed by",
    "resolved by",
    # Test/result claims
    "i've tested",
    "i have tested",
    "all tests pass",
    "the test passes",
    "everything works",
    "it's working",
    "it works now",
    "verified that",
    "confirmed that",
    "tested and",
    "all checks pass",
    "all linting passes",
    "no test failures",
    "every assertion passed",
    "test coverage is",
    # Structural/architectural claims without tools
    "the codebase has",
    "the project has",
    "the repository has",
    "the codebase uses",
    "the project uses",
    "the repository uses",
    "there are",
    "there is",
    "based on my analysis",
    "based on the analysis",
    "after analyzing",
    "after reviewing",
    "after inspecting",
    "looking at the code",
    "looking at the implementation",
    "from what i can see",
    "from what we can see",
    "the available files",
    "the related files",
    "the files you mentioned",
    "the files in this",
    # Recommendation/quality claims without tools
    "i recommend",
    "i suggest",
    "the best approach",
    "the optimal solution",
    "this is more efficient",
    "this is less efficient",
    "no security vulnerabilities",
    "all edge cases are handled",
    # Action claims without tools
    "let me walk you through",
    "here's a summary",
    "to summarize",
    "in summary",
    "i've analyzed",
    "i have analyzed",
    "i've inspected",
    "i have inspected",
    # Hedging/subtle claims
    "this should work",
    "that should work",
    "this will fix",
    "this is the right approach",
    "this is the correct",
    "this looks correct",
    "this looks good",
    "works as expected",
    "no breaking changes",
    "trust me",
    "rest assured",
    "i'm confident",
    "i'm sure that",
    "no further issues",
    "i just checked",
    "i double-checked",
    "i verified",
    "i confirmed",
]

# User mention patterns
_USER_MENTION_PATTERNS = [
    r"(?:the\s+)?(?:specific\s+)?files?\s+(?:you\s+)?(?:mentioned|said|referred\s+to|talked\s+about)",
    r"you\s+(?:mentioned|said)\s+(?:the\s+)?(?:files?\s+)?[`\"']?([^\s`\"'.]+\.\w+)",
    r"(?:files?\s+)?[`\"']([^\s`\"'.]+\.\w+)[`\"']\s+(?:and|that|you)",
    r"(?:mentioned|said)\s+(?:the\s+)?(?:files?\s+)?[`\"']?([^\s`\"'.]+\.\w+)",
]

# Sentence patterns to strip during sanitization
_STRIP_PATTERNS = [
    r"\bthe\s+(?:files?|code)\s+(?:you\s+)?(?:mentioned|said)\b",
    r"\byou\s+(?:mentioned|said)\s+(?:the\s+)?(?:files?)\b",
    r"\bthe\s+available\s+files?\s+(?:are|is|related)\b",
    r"\brelated\s+files?\s+(?:are|is)\b",
    r"\bthere\s+(?:are|is)\s+\d+\s+(?:files?|classes?|functions?|methods?)\b",
    r"\bthe\s+(?:codebase|project|repo)\s+(?:has|contains?|includes?)\b",
    r"\bbased\s+on\s+(?:my\s+)?(?:analysis|review)\b",
    r"\bafter\s+(?:analyzing|reviewing|inspecting)\b",
    # Hedging patterns
    r"\bthis\s+should\s+(?:now\s+)?(?:work|function|run|fix|resolve)\b",
    r"\bthis\s+(?:looks?|seems?|appears?)\s+(?:correct|right|good|fine|ok)\b",
    r"\bworks?\s+as\s+(?:expected|intended|designed)\b",
    r"\bno\s+breaking\s+changes?\b",
    r"\bno\s+(?:further|additional)\s+(?:issues?|problems?)\b",
    r"\bshouldn't\s+(?:cause|produce|introduce)\b",
    r"\btrust\s+me\b",
    r"\brest\s+assured\b",
    r"\bi(?:'m| am)\s+confident\b",
    r"\bi(?:'m| am)\s+sure\b",
]

# File extensions for validation
_CODE_EXTS = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".c++": "cpp",
    ".cxx": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".swift": "swift",
    ".scala": "scala",
    ".dart": "dart",
    ".m": "objc",
    ".h": "c",
    ".hpp": "cpp",
}

# ---- Hedging / Subtle Unverifiable Claims ----
# These are claims that sound confident but are actually unverifiable without tools.
# The LLM uses these to avoid being caught by direct fabrication detection.
_HEDGING_PHRASES = [
    # "Should work" family - implies confidence without verification
    r"\bthis\s+should\s+(?:now\s+)?(?:work|function|run|fix|resolve|handle)\b",
    r"\bthat\s+should\s+(?:now\s+)?(?:work|function|run|fix|resolve|handle)\b",
    r"\bit\s+should\s+(?:now\s+)?(?:work|function|run|be\s+working)\b",
    r"\bthis\s+will\s+(?:fix|resolve|handle|solve|address)\b",
    r"\bthat\s+will\s+(?:fix|resolve|handle|solve|address)\b",
    r"\bthis\s+(?:change|fix|patch|modification)\s+should\b",
    # "Right approach" family - claims correctness without evidence
    r"\bthis\s+is\s+(?:the\s+)?(?:right|correct|proper|best|appropriate)\s+(?:approach|way|solution|method|fix)\b",
    r"\bthis\s+(?:looks?|seems?|appears?)\s+(?:correct|right|good|fine|ok|okay)\b",
    r"\bthis\s+(?:looks?|seems?|appears?)\s+(?:like\s+)?(?:the\s+)?(?:right|correct|proper)\b",
    # "Trust me" family - asking for trust without evidence
    r"\btrust\s+me\b",
    r"\bbelieve\s+me\b",
    r"\brest\s+assured\b",
    r"\byou\s+can\s+(?:trust|rely|depend)\b",
    # "I'm confident" family - expressing confidence without verification
    r"\bi(?:'m| am)\s+(?:fairly|quite|very|extremely|pretty)\s+confident\b",
    r"\bi(?:'m| am)\s+confident\s+(?:that\s+)?(?:this|it)\b",
    r"\bi(?:'m| am)\s+sure\s+(?:that\s+)?(?:this|it)\b",
    # "No issues" family - claiming absence of problems without scanning
    r"\bno\s+(?:(?:further|additional|other|more)\s+)?(?:issues?|problems?|bugs?|errors?|concerns?)\s+(?:should|will|would)\b",
    r"\bshouldn't\s+(?:cause|produce|introduce|have)\s+(?:any\s+)?(?:issues?|problems?|bugs?|errors?)\b",
    r"\b(?:won't|will\s+not)\s+(?:cause|produce|introduce|have)\s+(?:any\s+)?(?:issues?|problems?|bugs?|errors?)\b",
    # "Works as expected" family
    r"\bworks?\s+as\s+(?:expected|intended|designed|specified)\b",
    r"\bbehaves?\s+as\s+(?:expected|intended|designed|specified)\b",
    # "This covers" family - claiming completeness without verification
    r"\bthis\s+covers?\s+(?:all|every|the\s+(?:required|necessary|needed))\b",
    r"\bthis\s+(?:handles?|accounts?\s+for)\s+(?:all|every)\b",
    r"\bthis\s+(?:should|will)\s+(?:handle|cover|address|manage)\s+(?:all|every)\b",
    # "No breaking changes" family - claiming safety without testing
    r"\bno\s+breaking\s+changes?\b",
    r"\b(?:won't|will\s+not)\s+break\s+(?:anything|existing|current|backward)\b",
    r"\bbackward[\s-]compatible\b",
    # Subtle "I checked" without tool
    r"\bi\s+(?:just\s+)?(?:checked|verified|confirmed|validated)\b",
    r"\bquick(?:ly)?\s+(?:checked|verified|confirmed|validated)\b",
    r"\bdouble[\s-]checked\b",
]

# Strip patterns for hedging phrases
_STRIP_HEDGING = [
    r"\bthis\s+should\s+(?:now\s+)?(?:work|function|run|fix|resolve)\b",
    r"\bthis\s+(?:looks?|seems?|appears?)\s+(?:correct|right|good|fine|ok)\b",
    r"\bworks?\s+as\s+(?:expected|intended|designed)\b",
    r"\bno\s+breaking\s+changes?\b",
    r"\bno\s+(?:further|additional)\s+(?:issues?|problems?)\b",
    r"\bshouldn't\s+(?:cause|produce|introduce)\b",
]


# ---- Tool Result Integrity ----


class ToolResultIntegrity:
    """Track tool result integrity to detect plugin tampering."""

    def __init__(self) -> None:
        self._original_hashes: dict[str, str] = {}
        self._original_results: dict[str, str] = {}

    def record_original(self, tool_name: str, args: dict, result: str) -> str:
        """Record original tool result and return its hash."""
        key = self._make_key(tool_name, args)
        result_hash = hashlib.sha256(result.encode("utf-8")).hexdigest()[:16]
        self._original_hashes[key] = result_hash
        self._original_results[key] = result[:500]  # Store first 500 chars
        return result_hash

    def check_after_plugin(self, tool_name: str, args: dict, result: str) -> list[str]:
        """Check if plugin modified the result. Returns list of issues."""
        issues = []
        key = self._make_key(tool_name, args)

        if key not in self._original_hashes:
            return issues

        original_hash = self._original_hashes[key]
        new_hash = hashlib.sha256(result.encode("utf-8")).hexdigest()[:16]

        if original_hash != new_hash:
            original_preview = self._original_results.get(key, "")[:100]
            new_preview = result[:100]
            issues.append(
                f"Tool result integrity: '{tool_name}' result was modified by plugin. "
                f"Original hash: {original_hash}, New hash: {new_hash}. "
                f"Original preview: '{original_preview}...' -> "
                f"New preview: '{new_preview}...'"
            )

        return issues

    def _make_key(self, tool_name: str, args: dict) -> str:
        """Create a unique key for a tool call."""
        import json

        args_str = json.dumps(args, sort_keys=True, default=str)
        return f"{tool_name}:{hashlib.md5(args_str.encode()).hexdigest()[:8]}"


# Singleton for tool result integrity
_tool_integrity: ToolResultIntegrity | None = None


def get_tool_integrity() -> ToolResultIntegrity:
    """Get or create the singleton ToolResultIntegrity tracker."""
    global _tool_integrity
    if _tool_integrity is None:
        _tool_integrity = ToolResultIntegrity()
    return _tool_integrity


def _detect_fabrication_phrases(content: str, tool_history: list[dict]) -> list[str]:
    """Detect fabrication phrases in content."""
    issues = []
    tools_called = {tc.get("tool", "") for tc in tool_history}

    for pattern in _FABRICATION_PHRASES:
        for match in re.finditer(pattern, content, re.IGNORECASE):
            phrase = match.group(0)

            # Determine which category this pattern belongs to by checking against
            # the original phrase list indices (test/lint/build, read/verify, fix/edit)
            matched = False

            # Test/lint/build claims (indices 4-11 of _FABRICATION_PHRASES)
            _TEST_LINT_PATTERNS = _FABRICATION_PHRASES[4:12]
            # Read/verify claims (indices 0-3, 20-21 of _FABRICATION_PHRASES)
            _READ_VERIFY_PATTERNS = _FABRICATION_PHRASES[0:4] + _FABRICATION_PHRASES[20:22]
            # Fix/edit claims (indices 12-15 of _FABRICATION_PHRASES)
            _FIX_EDIT_PATTERNS = _FABRICATION_PHRASES[12:16]

            for cat_pattern in _TEST_LINT_PATTERNS:
                if re.search(cat_pattern, phrase, re.IGNORECASE):
                    if "execute_shell" not in tools_called:
                        issues.append(
                            f"Fabrication: '{phrase}' — no test/lint/build tool was called"
                        )
                    matched = True
                    break

            if not matched:
                for cat_pattern in _READ_VERIFY_PATTERNS:
                    if re.search(cat_pattern, phrase, re.IGNORECASE):
                        read_tools = {"read_file", "grep_content", "grep", "ast_grep"}
                        if not (read_tools & tools_called):
                            issues.append(
                                f"Fabrication: '{phrase}' — no read/verify tool was called"
                            )
                        matched = True
                        break

            if not matched:
                for cat_pattern in _FIX_EDIT_PATTERNS:
                    if re.search(cat_pattern, phrase, re.IGNORECASE):
                        write_tools = {"write_file", "edit_file"}
                        if not (write_tools & tools_called):
                            issues.append(f"Fabrication: '{phrase}' — no fix/edit tool was called")
                        matched = True
                        break

            # Catch-all: if phrase matched but not in any category, flag if no tools
            if not matched and not tools_called:
                issues.append(f"Fabrication: '{phrase}' — no tools called to verify")

    return issues


def _detect_hedging_phrases(content: str, tool_history: list[dict]) -> list[str]:
    """Detect hedging/subtle unverifiable claims.

    These are phrases where the LLM sounds confident but hasn't actually
    verified anything with tools. They slip past fabrication detection
    because they don't directly claim a specific verifiable fact.
    """
    issues = []
    if not content:
        return issues

    tools_called = {tc.get("tool", "") for tc in tool_history}

    # High-priority patterns that should always be flagged
    _ALWAYS_FLAG = [
        (r"\btrust\s+me\b", "trust me"),
        (r"\bbelieve\s+me\b", "believe me"),
        (r"\brest\s+assured\b", "rest assured"),
        (r"\bi(?:'m| am)\s+confident\b", "confidence claim"),
        (r"\bi(?:'m| am)\s+sure\b", "certainty claim"),
    ]

    for pattern, label in _ALWAYS_FLAG:
        for match in re.finditer(pattern, content, re.IGNORECASE):
            phrase = match.group(0)
            issues.append(f"Hedging: '{phrase}' — appeal to trust/certainty without evidence")

    for pattern in _HEDGING_PHRASES:
        for match in re.finditer(pattern, content, re.IGNORECASE):
            phrase = match.group(0)
            phrase_lower = phrase.lower()

            # Skip if already caught by always-flag patterns
            if any(re.search(p, phrase, re.IGNORECASE) for p, _ in _ALWAYS_FLAG):
                continue

            # "should work" without having actually run/tested
            if "should" in phrase_lower and (
                "work" in phrase_lower or "fix" in phrase_lower or "resolve" in phrase_lower
            ):
                if "execute_shell" not in tools_called and "run" not in tools_called:
                    issues.append(
                        f"Hedging: '{phrase}' — claims correctness without running/testing"
                    )
                    continue

            # "checked/verified/confirmed" without read/grep tools
            if any(
                w in phrase_lower
                for w in ("checked", "verified", "confirmed", "validated", "double-checked")
            ):
                read_tools = {"read_file", "grep_content", "grep", "ast_grep", "glob_files"}
                if not (read_tools & tools_called):
                    issues.append(
                        f"Hedging: '{phrase}' — claims verification without read/grep tools"
                    )
                    continue

            # "this is the right/approach" — correctness claims
            if "right" in phrase_lower or "correct" in phrase_lower or "proper" in phrase_lower:
                if not tools_called:
                    issues.append(f"Hedging: '{phrase}' — correctness claim without any tool usage")
                    continue

            # "no breaking changes" — safety claims
            if "breaking" in phrase_lower or "backward" in phrase_lower:
                test_tools = {"execute_shell", "run_tests"}
                if not (test_tools & tools_called):
                    issues.append(f"Hedging: '{phrase}' — safety claim without testing")
                    continue

            # Generic hedge without tools
            if not tools_called:
                issues.append(f"Hedging: '{phrase}' — claim made without any tool usage")

    return issues


def _detect_inline_fabrication(content: str, tool_history: list[dict]) -> list[str]:
    """Detect fabrication when no tool calls were made (inline check)."""
    if not tool_history:
        content_lower = content.lower()
        for phrase in _INLINE_FABRICATION_PHRASES:
            if phrase in content_lower:
                return [f"Inline fabrication: '{phrase}' — no tools called to verify"]
    return []


def _verify_claims(content: str, tool_history: list[dict]) -> list[str]:
    """Cross-reference claims against tool history."""
    issues = []
    if not content:
        return issues

    content_lower = content.lower()
    tools_called = {tc.get("tool", "") for tc in tool_history}

    # Collect all file paths touched by tools
    all_tool_files: set[str] = set()
    for tc in tool_history:
        args = tc.get("args", {})
        for key in ("file_path", "path", "target_file", "directory"):
            val = args.get(key, "")
            if val:
                all_tool_files.add(val.lower())
                all_tool_files.add(os.path.basename(val).lower())
        result = str(tc.get("result", ""))
        for file_match in re.finditer(r"[\w\-/]+\.\w+", result):
            all_tool_files.add(file_match.group(0).lower())

    # Check "I read X" claims
    read_calls = [
        tc
        for tc in tool_history
        if tc.get("tool") in ("read_file", "grep_content", "grep", "ast_grep")
    ]
    read_claims = re.findall(
        r"(?:i\s+read|reading|examined?|inspected?|looked\s+at|checked|reviewed)\s+(?:the\s+)?(?:file\s+)?[`\"']?([^\s`\"'.]+\.\w+)",
        content_lower,
    )
    for claimed_file in read_claims:
        if not read_calls:
            issues.append(
                f"Claims to have read '{claimed_file}' but no read/search tool was called"
            )

    # Check "I created/wrote X" claims
    write_calls = [tc for tc in tool_history if tc.get("tool") in ("write_file", "edit_file")]
    write_claims = re.findall(
        r"(?:i\s+(?:created|wrote|saved|added|generated|built|produced)|(?:created|wrote|saved|added|generated|built)\s+the\s+file)[\s]+[`\"']?([^\s`\"'.]+\.\w+)",
        content_lower,
    )
    for claimed_file in write_claims:
        if not write_calls:
            issues.append(
                f"Claims to have created '{claimed_file}' but no write_file/edit_file tool was called"
            )

    # Check "tests pass" claims
    test_claims = [
        "all tests pass",
        "tests pass",
        "test passes",
        "all tests passed",
        "tests passed",
        "test passed",
        "all tests are passing",
    ]
    if any(claim in content_lower for claim in test_claims):
        shell_calls = [tc for tc in tool_history if tc.get("tool") == "execute_shell"]
        if not shell_calls:
            issues.append("Claims tests pass but no execute_shell tool was called")

    # Check "I fixed X" claims
    fix_claims = [
        "fixed the",
        "resolved the",
        "patched the",
        "corrected the",
        "i fixed",
        "i resolved",
        "i patched",
        "i corrected",
    ]
    if any(claim in content_lower for claim in fix_claims):
        if not write_calls:
            issues.append("Claims to have fixed something but no edit_file/write_file was called")

    # Check "I searched/found" claims
    search_claim_phrases = [
        "i searched for",
        "i found that",
        "searching revealed",
        "grepping showed",
        "grep shows",
        "rg shows",
        "i located",
        "the search found",
    ]
    if any(claim in content_lower for claim in search_claim_phrases):
        search_tools = {
            "grep_content",
            "grep",
            "rg",
            "ast_grep",
            "search_symbol",
            "glob_files",
            "file_search",
        }
        if not (search_tools & tools_called):
            issues.append("Claims to have searched/found something but no search tool was called")

    # Check "I analyzed/inspected" claims
    analyze_claims = [
        "i analyzed",
        "i examined",
        "i inspected",
        "i reviewed",
        "after analyzing",
        "upon inspection",
        "looking at the code",
        "examining the",
        "reviewing the",
    ]
    if any(claim in content_lower for claim in analyze_claims):
        read_tools = {"read_file", "grep_content", "grep", "ast_grep"}
        if not (read_tools & tools_called):
            issues.append("Claims to have analyzed/inspected but no read/search tool was called")

    # Check "I ran/executed" claims
    exec_claims = [
        "i ran the",
        "i executed the",
        "i ran a",
        "i executed a",
        "running the tests",
        "executing the tests",
        "the command succeeded",
        "the output shows",
    ]
    if any(claim in content_lower for claim in exec_claims):
        if "execute_shell" not in tools_called:
            issues.append(
                "Claims to have run/executed something but no execute_shell tool was called"
            )

    # Check "user mentioned" fabrication
    for pat in _USER_MENTION_PATTERNS:
        for match in re.finditer(pat, content, re.IGNORECASE):
            claimed_files = [match.group(1)] if match.lastindex and match.group(1) else []
            # Extract sentence
            sentence_end = -1
            search_from = match.end()
            while True:
                dot_pos = content.find(".", search_from)
                if dot_pos == -1:
                    break
                after_dot = dot_pos + 1
                if after_dot >= len(content) or content[after_dot] in (" ", "\n", "\r", "\t", ")"):
                    sentence_end = dot_pos + 1
                    break
                search_from = dot_pos + 1
            if sentence_end == -1:
                sentence_end = min(match.end() + 200, len(content))
            snippet = content[match.start() : sentence_end]
            quoted_files = re.findall(r"[`\"']([^\s`\"'.]+\.\w+)[`\"']", snippet)
            all_claimed = set(claimed_files) | set(quoted_files)
            for cf in all_claimed:
                if cf not in all_tool_files and not os.path.exists(cf):
                    issue = f"Claims user mentioned '{cf}' but this file was not found via any tool"
                    if issue not in issues:
                        issues.append(issue)

    # Check file listing without search tools
    search_tools = {
        "grep_content",
        "grep",
        "rg",
        "ast_grep",
        "search_symbol",
        "glob_files",
        "file_search",
        "directory_scanner",
    }
    has_search = bool(search_tools & tools_called)
    has_read = any(t in tools_called for t in ("read_file", "grep_content"))
    if not has_search and not has_read:
        file_listing_pattern = r"(?:^|\n)\s*(?:\d+\.\s*|[-*]\s*)[`\"']?([\w\-/]+\.\w+)[`\"']?"
        file_listings = re.findall(file_listing_pattern, content)
        if len(file_listings) >= 2:
            issues.append(
                f"Lists specific files ({', '.join(file_listings[:3])}) without using search/glob/read tools"
            )

    # Check file path references
    _FILE_EXTS = (".py", ".js", ".ts", ".go", ".rs", ".java", ".c", ".cpp", ".tsx", ".jsx", ".pyc")
    file_path_patterns = [
        r"(?:`|\"|')((?:\./|\.\./|\w+/)*[\w\-]+\.\w+)(?:`|\"|')",
        r"\b([\w\-/]+\.(?:py|js|ts|go|rs|java|c|cpp|tsx|jsx|pyc))\b",
        r"\b([\w\-]+\.cpython-\d+\.\w+)\b",
    ]
    for pat in file_path_patterns:
        for match in re.finditer(pat, content):
            path = match.group(1)
            if path.endswith(_FILE_EXTS) or "/" in path:
                if not os.path.exists(path) and not path.startswith("./"):
                    if path not in all_tool_files and os.path.basename(path) not in all_tool_files:
                        issues.append(
                            f"Referenced file '{path}' may not exist and was not accessed via tools"
                        )

    return issues


def _validate_code_blocks(content: str) -> list[str]:
    """Validate code blocks for syntax errors."""
    issues = []

    # Python syntax validation
    py_pattern = r"```(?:python|py)\s*\n(.*?)```"
    for match in re.finditer(py_pattern, content, re.DOTALL):
        code = match.group(1).strip()
        if not code:
            continue
        try:
            ast.parse(code)
        except SyntaxError as e:
            issues.append(f"Python syntax error: {e}")

    # Multi-language brace matching
    brace_langs = {
        "javascript": ("js",),
        "typescript": ("ts", "tsx"),
        "go": ("go",),
        "rust": ("rs",),
        "java": ("java",),
        "c": ("c",),
        "cpp": ("cpp", "c++", "cxx"),
        "csharp": ("cs",),
        "kotlin": ("kt", "kts"),
        "swift": ("swift",),
        "ruby": ("rb",),
        "php": ("php",),
        "scala": ("scala",),
        "objc": ("m",),
        "dart": ("dart",),
    }
    for lang, extensions in brace_langs.items():
        alt_pattern = "|".join(re.escape(ext) for ext in extensions)
        code_block_pattern = rf"```(?:{re.escape(lang)}|{alt_pattern})\s*\n(.*?)```"
        for match in re.finditer(code_block_pattern, content, re.DOTALL):
            code = match.group(1).strip()
            if not code:
                continue
            depth = 0
            for ch in code:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                if depth < 0:
                    issues.append(f"{lang.title()} code block has unbalanced braces")
                    break
            if depth > 0:
                issues.append(f"{lang.title()} code block has {depth} unclosed brace(s)")

    return issues


def _external_syntax_check(content: str) -> list[str]:
    """Run external syntax checkers on code blocks (py_compile, gofmt, etc.)."""
    issues = []

    # Python: use py_compile
    py_pattern = r"```(?:python|py)\s*\n(.*?)```"
    for match in re.finditer(py_pattern, content, re.DOTALL):
        code = match.group(1).strip()
        if not code or len(code) < _MIN_CODE_LENGTH:
            continue
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(code)
                f.flush()
                tmp_path = f.name
            result = subprocess.run(
                ["python", "-m", "py_compile", tmp_path],
                capture_output=True,
                text=True,
                timeout=_SYNTAX_CHECK_TIMEOUT,
            )
            if result.returncode != 0:
                issues.append(f"Python compilation error: {result.stderr.strip()[:200]}")
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    # Go: use gofmt
    go_pattern = r"```go\s*\n(.*?)```"
    for match in re.finditer(go_pattern, content, re.DOTALL):
        code = match.group(1).strip()
        if not code or len(code) < _MIN_CODE_LENGTH:
            continue
        try:
            result = subprocess.run(
                ["gofmt", "-e"],
                input=code,
                capture_output=True,
                text=True,
                timeout=_SYNTAX_CHECK_TIMEOUT,
            )
            if result.returncode != 0:
                issues.append(f"Go format error: {result.stderr.strip()[:_ERROR_MESSAGE_MAX_LEN]}")
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

    # Rust: use rustfmt
    rs_pattern = r"```rust\s*\n(.*?)```"
    for match in re.finditer(rs_pattern, content, re.DOTALL):
        code = match.group(1).strip()
        if not code or len(code) < _MIN_CODE_LENGTH:
            continue
        try:
            result = subprocess.run(
                ["rustfmt", "--check"],
                input=code,
                capture_output=True,
                text=True,
                timeout=_SYNTAX_CHECK_TIMEOUT,
            )
            if result.returncode != 0:
                issues.append(
                    f"Rust format error: {result.stdout.strip()[:_ERROR_MESSAGE_MAX_LEN]}"
                )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

    # JavaScript: use node --check
    js_pattern = r"```(?:javascript|js)\s*\n(.*?)```"
    for match in re.finditer(js_pattern, content, re.DOTALL):
        code = match.group(1).strip()
        if not code or len(code) < _MIN_CODE_LENGTH:
            continue
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
                f.write(code)
                f.flush()
                tmp_path = f.name
            result = subprocess.run(
                ["node", "--check", tmp_path],
                capture_output=True,
                text=True,
                timeout=_SYNTAX_CHECK_TIMEOUT,
            )
            if result.returncode != 0:
                issues.append(
                    f"JavaScript syntax error: {result.stderr.strip()[:_ERROR_MESSAGE_MAX_LEN]}"
                )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    # TypeScript: use npx tsc --noEmit or node --check on transpiled
    ts_pattern = r"```(?:typescript|ts|tsx)\s*\n(.*?)```"
    for match in re.finditer(ts_pattern, content, re.DOTALL):
        code = match.group(1).strip()
        if not code or len(code) < _MIN_CODE_LENGTH:
            continue
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
                f.write(code)
                f.flush()
                tmp_path = f.name
            result = subprocess.run(
                ["npx", "tsc", "--noEmit", "--allowJs", tmp_path],
                capture_output=True,
                text=True,
                timeout=_SYNTAX_CHECK_TIMEOUT,
            )
            if result.returncode != 0:
                issues.append(f"TypeScript error: {result.stderr.strip()[:_ERROR_MESSAGE_MAX_LEN]}")
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    # Java: use javac -proc:none
    java_pattern = r"```java\s*\n(.*?)```"
    for match in re.finditer(java_pattern, content, re.DOTALL):
        code = match.group(1).strip()
        if not code or len(code) < _MIN_CODE_LENGTH:
            continue
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
                f.write(code)
                f.flush()
                tmp_path = f.name
            result = subprocess.run(
                ["javac", "-proc:none", tmp_path],
                capture_output=True,
                text=True,
                timeout=_SYNTAX_CHECK_TIMEOUT,
            )
            if result.returncode != 0:
                issues.append(
                    f"Java compilation error: {result.stderr.strip()[:_ERROR_MESSAGE_MAX_LEN]}"
                )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    # C: use gcc -fsyntax-only
    c_pattern = r"```c\s*\n(.*?)```"
    for match in re.finditer(c_pattern, content, re.DOTALL):
        code = match.group(1).strip()
        if not code or len(code) < _MIN_CODE_LENGTH:
            continue
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".c", delete=False) as f:
                f.write(code)
                f.flush()
                tmp_path = f.name
            result = subprocess.run(
                ["gcc", "-fsyntax-only", "-std=c11", tmp_path],
                capture_output=True,
                text=True,
                timeout=_SYNTAX_CHECK_TIMEOUT,
            )
            if result.returncode != 0:
                issues.append(f"C syntax error: {result.stderr.strip()[:_ERROR_MESSAGE_MAX_LEN]}")
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    # C++: use g++ -fsyntax-only
    cpp_pattern = r"```(?:cpp|c\+\+)\s*\n(.*?)```"
    for match in re.finditer(cpp_pattern, content, re.DOTALL):
        code = match.group(1).strip()
        if not code or len(code) < _MIN_CODE_LENGTH:
            continue
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".cpp", delete=False) as f:
                f.write(code)
                f.flush()
                tmp_path = f.name
            result = subprocess.run(
                ["g++", "-fsyntax-only", "-std=c++17", tmp_path],
                capture_output=True,
                text=True,
                timeout=_SYNTAX_CHECK_TIMEOUT,
            )
            if result.returncode != 0:
                issues.append(f"C++ syntax error: {result.stderr.strip()[:_ERROR_MESSAGE_MAX_LEN]}")
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    # Shell/Bash: use bash -n
    shell_pattern = r"```(?:bash|sh|shell|zsh)\s*\n(.*?)```"
    for match in re.finditer(shell_pattern, content, re.DOTALL):
        code = match.group(1).strip()
        if not code or len(code) < _MIN_CODE_LENGTH:
            continue
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
                f.write(code)
                f.flush()
                tmp_path = f.name
            result = subprocess.run(
                ["bash", "-n", tmp_path],
                capture_output=True,
                text=True,
                timeout=_SYNTAX_CHECK_TIMEOUT,
            )
            if result.returncode != 0:
                issues.append(
                    f"Shell syntax error: {result.stderr.strip()[:_ERROR_MESSAGE_MAX_LEN]}"
                )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    # Ruby: use ruby -c
    ruby_pattern = r"```(?:ruby|rb)\s*\n(.*?)```"
    for match in re.finditer(ruby_pattern, content, re.DOTALL):
        code = match.group(1).strip()
        if not code or len(code) < _MIN_CODE_LENGTH:
            continue
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".rb", delete=False) as f:
                f.write(code)
                f.flush()
                tmp_path = f.name
            result = subprocess.run(
                ["ruby", "-c", tmp_path],
                capture_output=True,
                text=True,
                timeout=_SYNTAX_CHECK_TIMEOUT,
            )
            if result.returncode != 0:
                issues.append(
                    f"Ruby syntax error: {result.stderr.strip()[:_ERROR_MESSAGE_MAX_LEN]}"
                )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    # PHP: use php -l
    php_pattern = r"```php\s*\n(.*?)```"
    for match in re.finditer(php_pattern, content, re.DOTALL):
        code = match.group(1).strip()
        if not code or len(code) < _MIN_CODE_LENGTH:
            continue
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".php", delete=False) as f:
                f.write(code)
                f.flush()
                tmp_path = f.name
            result = subprocess.run(
                ["php", "-l", tmp_path],
                capture_output=True,
                text=True,
                timeout=_SYNTAX_CHECK_TIMEOUT,
            )
            if result.returncode != 0:
                issues.append(f"PHP syntax error: {result.stderr.strip()[:_ERROR_MESSAGE_MAX_LEN]}")
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    # Kotlin: use kotlinc -script or ktlint
    kotlin_pattern = r"```(?:kotlin|kt)\s*\n(.*?)```"
    for match in re.finditer(kotlin_pattern, content, re.DOTALL):
        code = match.group(1).strip()
        if not code or len(code) < _MIN_CODE_LENGTH:
            continue
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".kt", delete=False) as f:
                f.write(code)
                f.flush()
                tmp_path = f.name
            result = subprocess.run(
                ["ktlint", "--format", tmp_path],
                capture_output=True,
                text=True,
                timeout=_SYNTAX_CHECK_TIMEOUT,
            )
            if result.returncode != 0:
                result = subprocess.run(
                    ["kotlinc", "-script", tmp_path],
                    capture_output=True,
                    text=True,
                    timeout=_SYNTAX_CHECK_TIMEOUT,
                )
                if result.returncode != 0:
                    issues.append(f"Kotlin error: {result.stderr.strip()[:_ERROR_MESSAGE_MAX_LEN]}")
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    # Swift: use swiftc -parse
    swift_pattern = r"```swift\s*\n(.*?)```"
    for match in re.finditer(swift_pattern, content, re.DOTALL):
        code = match.group(1).strip()
        if not code or len(code) < _MIN_CODE_LENGTH:
            continue
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".swift", delete=False) as f:
                f.write(code)
                f.flush()
                tmp_path = f.name
            result = subprocess.run(
                ["swiftc", "-parse", tmp_path],
                capture_output=True,
                text=True,
                timeout=_SYNTAX_CHECK_TIMEOUT,
            )
            if result.returncode != 0:
                issues.append(
                    f"Swift syntax error: {result.stderr.strip()[:_ERROR_MESSAGE_MAX_LEN]}"
                )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    # Scala: use scalac -print
    scala_pattern = r"```scala\s*\n(.*?)```"
    for match in re.finditer(scala_pattern, content, re.DOTALL):
        code = match.group(1).strip()
        if not code or len(code) < _MIN_CODE_LENGTH:
            continue
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".scala", delete=False) as f:
                f.write(code)
                f.flush()
                tmp_path = f.name
            result = subprocess.run(
                ["scalac", "-print", tmp_path],
                capture_output=True,
                text=True,
                timeout=_SYNTAX_CHECK_TIMEOUT,
            )
            if result.returncode != 0:
                issues.append(f"Scala error: {result.stderr.strip()[:_ERROR_MESSAGE_MAX_LEN]}")
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    # C#: use dotnet-script or csc
    csharp_pattern = r"```(?:csharp|cs)\s*\n(.*?)```"
    for match in re.finditer(csharp_pattern, content, re.DOTALL):
        code = match.group(1).strip()
        if not code or len(code) < _MIN_CODE_LENGTH:
            continue
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".cs", delete=False) as f:
                f.write(code)
                f.flush()
                tmp_path = f.name
            result = subprocess.run(
                ["dotnet", "script", tmp_path],
                capture_output=True,
                text=True,
                timeout=_SYNTAX_CHECK_TIMEOUT,
            )
            if result.returncode != 0:
                issues.append(f"C# error: {result.stderr.strip()[:_ERROR_MESSAGE_MAX_LEN]}")
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    return issues


def _compute_confidence(
    content: str,
    tool_history: list[dict],
    fabrication_issues: list[str],
    code_issues: list[str],
    claim_issues: list[str],
    external_issues: list[str],
) -> int:
    """Compute confidence score (0-100)."""
    score = 100

    # Deductions per issue type (higher = more severe)
    FABRICATION_PENALTY = 15
    CODE_PENALTY = 10
    CLAIM_PENALTY = 12
    EXTERNAL_PENALTY = 8
    NO_TOOLS_PENALTY = 20
    SHORT_RESPONSE_PENALTY = 15
    MEDIUM_RESPONSE_PENALTY = 5
    LONG_NO_TOOL_PENALTY = 20
    TOOL_SUCCESS_BONUS = 5
    TOOL_DIVERSITY_BONUS = 5
    MULTI_FABRICATION_PENALTY = 10

    # Deductions for hallucination indicators
    score -= len(fabrication_issues) * FABRICATION_PENALTY
    score -= len(code_issues) * CODE_PENALTY
    score -= len(claim_issues) * CLAIM_PENALTY
    score -= len(external_issues) * EXTERNAL_PENALTY

    # Deductions for missing tool usage
    if not tool_history:
        score -= NO_TOOLS_PENALTY

    # Deductions for response length issues
    if content and len(content.strip()) < 50:
        score -= SHORT_RESPONSE_PENALTY
    elif content and len(content.strip()) < 100:
        score -= MEDIUM_RESPONSE_PENALTY

    # Deductions for suspiciously long responses without tools
    if content and len(content) > 5000 and not tool_history:
        score -= LONG_NO_TOOL_PENALTY

    # Bonus for proper tool usage
    if tool_history:
        successful = sum(1 for t in tool_history if t.get("success", True))
        total = len(tool_history)
        if total > 0 and successful / total >= 0.8:
            score += TOOL_SUCCESS_BONUS

    # Bonus for tool diversity
    if tool_history:
        unique_tools = len(set(tc.get("tool", "") for tc in tool_history))
        if unique_tools >= 3:
            score += TOOL_DIVERSITY_BONUS

    # Heavy penalty for multiple fabrication signals
    fabrication_count = sum(1 for issue in fabrication_issues if "Fabrication:" in issue)
    if fabrication_count >= 3:
        score -= MULTI_FABRICATION_PENALTY

    return max(0, min(100, score))


def _sanitize_content(content: str, issues: list[str]) -> str:
    """Remove sentences containing hallucinated claims."""
    if not content or not issues:
        return content

    # Extract file names mentioned in issues
    hallucinated_files = set()
    for issue in issues:
        for match in re.finditer(r"'([^']+)'", issue):
            val = match.group(1)
            if "." in val:
                hallucinated_files.add(val.lower())

    # Split into sentences
    sentences = re.split(r"(?<=[.!?])\s+|\n{2,}", content)
    cleaned = []
    for sentence in sentences:
        sentence_lower = sentence.lower()
        is_hallucinated = False

        # Check hallucinated file references
        for hf in hallucinated_files:
            if hf in sentence_lower:
                is_hallucinated = True
                break

        # Check fabrication patterns
        for pat in _STRIP_PATTERNS:
            if re.search(pat, sentence_lower):
                is_hallucinated = True
                break

        if not is_hallucinated:
            cleaned.append(sentence)

    return " ".join(cleaned)


class ResponseVerifier:
    """Unified response verification pipeline for all execution paths."""

    def __init__(
        self,
        enable_external_checks: bool = True,
        auto_sanitize: bool = True,
        confidence_threshold: int = 50,
    ):
        self.enable_external_checks = enable_external_checks
        self.auto_sanitize = auto_sanitize
        self.confidence_threshold = confidence_threshold

    def verify(
        self,
        content: str,
        tool_history: list[dict] | None = None,
        task_type: str = "create",
        integrity_result: list[str] | None = None,
    ) -> VerificationResult:
        """Run the full verification pipeline on a response.

        Args:
            content: The LLM response content to verify.
            tool_history: List of tool calls made during execution.
            task_type: The type of task (chat, query, create, fix, analyze, test).
            integrity_result: Tool result integrity issues (from ToolResultIntegrity).

        Returns:
            VerificationResult with issues, confidence, and cleaned content.
        """
        tool_history = tool_history or []
        logger.info(
            "Verification starting: task_type=%s, content_len=%d, tool_calls=%d",
            task_type,
            len(content),
            len(tool_history),
        )
        logger.debug("Content preview: %.200s", content)

        # Skip verification for simple chat with no tools
        if task_type == "chat" and not tool_history:
            return VerificationResult(
                original_content=content,
                cleaned_content=content,
                confidence=85,
            )

        # 1. Fabrication phrase detection
        fab_issues = _detect_fabrication_phrases(content, tool_history)
        logger.debug("Stage 1 - Fabrication phrases: %d issues", len(fab_issues))

        # 2. Inline fabrication detection (no-tool-call)
        inline_issues = _detect_inline_fabrication(content, tool_history)
        logger.debug("Stage 2 - Inline fabrication: %d issues", len(inline_issues))

        # 3. Claim vs tool-history verification
        claim_issues = _verify_claims(content, tool_history)
        logger.debug("Stage 3 - Claim verification: %d issues", len(claim_issues))

        # 4. Hedging/subtle claim detection
        hedging_issues = _detect_hedging_phrases(content, tool_history)
        logger.debug("Stage 4 - Hedging phrases: %d issues", len(hedging_issues))

        # 5. Code block syntax validation
        code_issues = _validate_code_blocks(content)
        logger.debug("Stage 5 - Code block syntax: %d issues", len(code_issues))

        # 6. External syntax checking
        external_issues = []
        if self.enable_external_checks:
            external_issues = _external_syntax_check(content)
            logger.debug("Stage 6 - External syntax check: %d issues", len(external_issues))

        # 7. Tool result integrity (plugin tamper detection)
        integrity_issues = integrity_result or []
        if integrity_issues:
            logger.debug("Stage 7 - Tool integrity: %d issues", len(integrity_issues))

        # Combine all issues
        all_issues = (
            fab_issues
            + inline_issues
            + claim_issues
            + hedging_issues
            + code_issues
            + external_issues
            + integrity_issues
        )

        # 8. Compute confidence
        confidence = _compute_confidence(
            content, tool_history, fab_issues, code_issues, claim_issues, external_issues
        )
        # Extra penalty for hedging and integrity issues
        confidence -= len(hedging_issues) * 8
        confidence -= len(integrity_issues) * 15
        confidence = max(0, min(100, confidence))
        logger.info(
            "Verification complete: confidence=%d, hallucinations=%s, total_issues=%d [fab=%d inline=%d claims=%d hedging=%d code=%d external=%d integrity=%d]",
            confidence,
            bool(all_issues),
            len(all_issues),
            len(fab_issues),
            len(inline_issues),
            len(claim_issues),
            len(hedging_issues),
            len(code_issues),
            len(external_issues),
            len(integrity_issues),
        )

        # 9. Sanitize content if needed
        cleaned_content = content
        sanitized = False
        if self.auto_sanitize and all_issues and confidence < self.confidence_threshold:
            logger.info(
                "Sanitizing content: confidence=%d < threshold=%d",
                confidence,
                self.confidence_threshold,
            )
            cleaned_content = _sanitize_content(content, all_issues)
            sanitized = cleaned_content != content
            logger.debug(
                "Sanitization result: sanitized=%s, content_change=%d chars",
                sanitized,
                len(content) - len(cleaned_content),
            )

        return VerificationResult(
            original_content=content,
            cleaned_content=cleaned_content,
            issues=fab_issues + inline_issues,
            code_issues=code_issues,
            claim_issues=claim_issues,
            external_issues=external_issues,
            hedging_issues=hedging_issues,
            integrity_issues=integrity_issues,
            confidence=confidence,
            has_hallucinations=bool(all_issues),
            sanitized=sanitized,
        )

    def verify_and_warn(
        self,
        content: str,
        tool_history: list[dict] | None = None,
        task_type: str = "create",
    ) -> tuple[str, str]:
        """Verify and return (cleaned_content, warning_message).

        Convenience method for execution paths that want to append warnings.
        """
        result = self.verify(content, tool_history, task_type)

        if not result.has_hallucinations:
            return result.cleaned_content, ""

        warning_lines = ["WARNING: This response may contain unverified claims:"]
        for issue in result.all_issues[:5]:
            warning_lines.append(f"  - {issue}")
        warning_lines.append("Treat these claims with skepticism. Verify independently.")

        return result.cleaned_content, "\n".join(warning_lines)


# Singleton for convenience
_verifier: ResponseVerifier | None = None


def get_verifier(**kwargs: Any) -> ResponseVerifier:
    """Get or create the singleton ResponseVerifier."""
    global _verifier
    if _verifier is None:
        _verifier = ResponseVerifier(**kwargs)
    return _verifier


def verify_response(
    content: str,
    tool_history: list[dict] | None = None,
    task_type: str = "create",
) -> VerificationResult:
    """Convenience function for quick verification."""
    return get_verifier().verify(content, tool_history, task_type)
