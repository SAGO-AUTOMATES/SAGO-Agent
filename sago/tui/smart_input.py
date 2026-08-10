"""Smart Input Processor

Extracts keywords, traces, errors, and key information from long inputs
to enable selective reading and token-efficient processing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class InputAnalysis:
    """Analysis result of user input."""

    original_length: int
    word_count: int
    needs_summarization: bool
    keywords: list[str] = field(default_factory=list)
    error_lines: list[str] = field(default_factory=list)
    stack_frames: list[str] = field(default_factory=list)
    file_references: list[str] = field(default_factory=list)
    code_blocks: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    numbers: list[str] = field(default_factory=list)
    importance_score: float = 0.0
    summary: str = ""
    selective_content: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_length": self.original_length,
            "word_count": self.word_count,
            "needs_summarization": self.needs_summarization,
            "keywords": self.keywords[:20],
            "error_count": len(self.error_lines),
            "stack_frame_count": len(self.stack_frames),
            "file_count": len(self.file_references),
            "code_block_count": len(self.code_blocks),
            "url_count": len(self.urls),
            "importance_score": round(self.importance_score, 3),
        }


# Patterns for extraction
ERROR_PATTERNS = [
    re.compile(r"(?:error|exception|traceback|failed|failure|fatal|panic)[^\n]*", re.IGNORECASE),
    re.compile(r'(?:Traceback|File\s+".*",\s*line\s+\d+)[^\n]*', re.IGNORECASE),
    re.compile(r"(?:Error|Exception|Warning):\s*[^\n]+"),
]

STACK_PATTERNS = [
    re.compile(r"at\s+([\w.]+)\(([^)]*)\)"),
    re.compile(r'File\s+"([^"]+)",\s*line\s+(\d+)'),
    re.compile(r"in\s+(\w+)\s+at\s+line\s+(\d+)"),
]

FILE_PATTERNS = [
    re.compile(r"(?:/[\w.-]+){2,}[\w.-]*\.\w+"),  # Unix paths
    re.compile(r"(?:[A-Z]:\\[\w.-]+\\)+[\w.-]+\.\w+"),  # Windows paths
    re.compile(
        r"[\w.-]+\.(?:py|js|ts|tsx|jsx|rs|go|java|c|cpp|h|hpp|rb|php|sh|yaml|yml|json|toml|xml|sql|md|txt)\b"
    ),
]

CODE_BLOCK_PATTERN = re.compile(r"```[\s\S]*?```", re.MULTILINE)
URL_PATTERN = re.compile(r"https?://\S+")
NUMBER_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\b")

# Keywords that indicate importance
IMPORTANCE_KEYWORDS = {
    "critical": 0.9,
    "urgent": 0.9,
    "bug": 0.8,
    "error": 0.8,
    "fix": 0.7,
    "security": 0.8,
    "vulnerability": 0.9,
    "implement": 0.6,
    "create": 0.6,
    "deploy": 0.7,
    "test": 0.5,
    "review": 0.5,
    "refactor": 0.5,
    "performance": 0.7,
    "optimize": 0.7,
    "slow": 0.6,
    "crash": 0.9,
    "fail": 0.8,
    "broken": 0.8,
    "todo": 0.4,
    "hack": 0.6,
    "workaround": 0.5,
}

# Keywords for task classification
TASK_KEYWORDS = {
    "debug": ["error", "bug", "crash", "fail", "traceback", "exception", "issue"],
    "implement": ["create", "add", "build", "new", "implement", "write", "develop"],
    "fix": ["fix", "repair", "patch", "resolve", "correct", "update"],
    "refactor": ["refactor", "clean", "reorganize", "restructure", "improve"],
    "test": ["test", "spec", "assert", "verify", "validate", "check"],
    "deploy": ["deploy", "release", "ship", "publish", "push", "launch"],
    "review": ["review", "check", "audit", "inspect", "analyze"],
    "optimize": ["optimize", "speed", "performance", "fast", "slow", "cache"],
    "security": ["security", "vulnerability", "auth", "encrypt", "token"],
}


class SmartInputProcessor:
    """Processes long inputs intelligently to save tokens."""

    WORD_THRESHOLD = 500
    TOKEN_RATIO = 4  # chars per token
    MAX_SUMMARY_TOKENS = 500
    MAX_SELECTIVE_TOKENS = 1000

    def analyze(self, text: str) -> InputAnalysis:
        """Analyze input text for smart processing."""
        words = text.split()
        word_count = len(words)

        analysis = InputAnalysis(
            original_length=len(text),
            word_count=word_count,
            needs_summarization=word_count > self.WORD_THRESHOLD,
        )

        # Extract components
        analysis.keywords = self._extract_keywords(text)
        analysis.error_lines = self._extract_errors(text)
        analysis.stack_frames = self._extract_stack_frames(text)
        analysis.file_references = self._extract_files(text)
        analysis.code_blocks = self._extract_code_blocks(text)
        analysis.urls = URL_PATTERN.findall(text)
        analysis.numbers = NUMBER_PATTERN.findall(text)

        # Calculate importance
        analysis.importance_score = self._calculate_importance(text, analysis)

        # Generate summary if needed
        if analysis.needs_summarization:
            analysis.summary = self._generate_summary(text, analysis)
            analysis.selective_content = self._extract_selective_content(text, analysis)

        return analysis

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract important keywords from text."""
        words = set(re.findall(r"\b\w+\b", text.lower()))
        keywords = []
        for word in words:
            if word in IMPORTANCE_KEYWORDS or len(word) > 6:
                keywords.append(word)
        return sorted(keywords)[:30]

    def _extract_errors(self, text: str) -> list[str]:
        """Extract error lines."""
        errors = []
        for pattern in ERROR_PATTERNS:
            matches = pattern.findall(text)
            errors.extend(matches)
        return list(dict.fromkeys(errors))[:20]  # Unique, max 20

    def _extract_stack_frames(self, text: str) -> list[str]:
        """Extract stack trace frames."""
        frames = []
        for pattern in STACK_PATTERNS:
            matches = pattern.findall(text)
            for match in matches:
                if isinstance(match, tuple) and len(match) >= 2:
                    frames.append(f"{match[0]}:{match[1]}")
                elif isinstance(match, tuple) and len(match) == 1:
                    frames.append(match[0])
                else:
                    frames.append(str(match))
        return frames[:20]

    def _extract_files(self, text: str) -> list[str]:
        """Extract file references."""
        files = []
        for pattern in FILE_PATTERNS:
            matches = pattern.findall(text)
            files.extend(matches)
        return list(dict.fromkeys(files))[:20]

    def _extract_code_blocks(self, text: str) -> list[str]:
        """Extract code blocks."""
        return CODE_BLOCK_PATTERN.findall(text)[:10]

    def _calculate_importance(self, text: str, analysis: InputAnalysis) -> float:
        """Calculate importance score (0-1)."""
        score = 0.5  # Base score

        # Boost for errors
        if analysis.error_lines:
            score += 0.2

        # Boost for stack traces
        if analysis.stack_frames:
            score += 0.1

        # Boost for keywords
        text_lower = text.lower()
        for keyword, weight in IMPORTANCE_KEYWORDS.items():
            if keyword in text_lower:
                score = max(score, weight)

        # Boost for questions
        if "?" in text:
            score += 0.05

        # Cap at 1.0
        return min(score, 1.0)

    def _generate_summary(self, text: str, analysis: InputAnalysis) -> str:
        """Generate a compact summary of the input."""
        parts = []

        # Main intent
        task_type = self._classify_task(text)
        if task_type:
            parts.append(f"Task: {task_type}")

        # Key points from first and last lines
        lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
        if lines:
            parts.append(f"Start: {lines[0][:150]}")
            if len(lines) > 1:
                parts.append(f"End: {lines[-1][:150]}")

        # Errors
        if analysis.error_lines:
            parts.append(f"Errors ({len(analysis.error_lines)}):")
            for err in analysis.error_lines[:3]:
                parts.append(f"  - {err[:200]}")

        # Stack frames
        if analysis.stack_frames:
            parts.append(f"Stack frames: {len(analysis.stack_frames)}")
            for frame in analysis.stack_frames[:3]:
                parts.append(f"  at {frame}")

        # Files
        if analysis.file_references:
            parts.append(f"Files: {', '.join(analysis.file_references[:5])}")

        # Code blocks
        if analysis.code_blocks:
            parts.append(f"Code blocks: {len(analysis.code_blocks)}")
            for i, block in enumerate(analysis.code_blocks[:2], 1):
                truncated = block[:300] + "..." if len(block) > 300 else block
                parts.append(f"  Block {i}:\n{truncated}")

        # Keywords
        if analysis.keywords:
            parts.append(f"Keywords: {', '.join(analysis.keywords[:10])}")

        return "\n".join(parts)

    def _extract_selective_content(self, text: str, analysis: InputAnalysis) -> str:
        """Extract the most important parts for selective reading."""
        parts = []

        # Add summary
        if analysis.summary:
            parts.append(analysis.summary)

        # Add first 200 words
        words = text.split()[:200]
        parts.append("First context: " + " ".join(words))

        # Add last 100 words
        if len(text.split()) > 300:
            words = text.split()[-100:]
            parts.append("Final context: " + " ".join(words))

        return "\n\n".join(parts)

    def _classify_task(self, text: str) -> str | None:
        """Classify the task type from text."""
        text_lower = text.lower()
        scores: dict[str, int] = {}

        for task_type, keywords in TASK_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                scores[task_type] = score

        if scores:
            best_task = max(scores.items(), key=lambda x: x[1])
            return best_task[0]
        return None

    def process_input(self, text: str) -> tuple[str, InputAnalysis]:
        """Process input and return optimized content + analysis."""
        analysis = self.analyze(text)

        if not analysis.needs_summarization:
            return text, analysis

        # Use selective content for long inputs
        return analysis.selective_content or analysis.summary, analysis


def get_smart_processor() -> SmartInputProcessor:
    """Get singleton smart processor."""
    return SmartInputProcessor()
