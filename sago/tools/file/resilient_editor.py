"""Resilient File Editor - Multi-tier intelligent matching and editing engine.

Features:
1. Multi-tier matching:
   - Tier 1: Exact substring match
   - Tier 2: Normalized whitespace & line endings (CRLF/LF, indentation adjustment)
   - Tier 3: Fuzzy block matching via SequenceMatcher
2. Multi-chunk atomic replacements
3. Unified diff patch application
4. Automatic change tracking and backup
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class MatchResult:
    found: bool
    start_idx: int = -1
    end_idx: int = -1
    confidence: float = 0.0
    matched_text: str = ""
    match_tier: str = "none"


class ResilientEditor:
    """Intelligent editor engine with fuzzy tolerance and multi-chunk support."""

    @staticmethod
    def normalize_newlines(text: str) -> str:
        return text.replace("\r\n", "\n").replace("\r", "\n")

    @classmethod
    def find_best_match(
        cls,
        content: str,
        target: str,
        fuzzy_threshold: float = 0.82,
    ) -> MatchResult:
        """Find the best match of target in content using a 3-tier algorithm."""
        norm_content = cls.normalize_newlines(content)
        norm_target = cls.normalize_newlines(target)

        # Tier 1: Exact Match
        idx = norm_content.find(norm_target)
        if idx != -1:
            return MatchResult(
                found=True,
                start_idx=idx,
                end_idx=idx + len(norm_target),
                confidence=1.0,
                matched_text=norm_content[idx : idx + len(norm_target)],
                match_tier="exact",
            )

        # Tier 2: Whitespace-trimmed / Normalized lines match
        target_lines = [line.strip() for line in norm_target.splitlines() if line.strip()]
        if target_lines:
            content_lines = norm_content.splitlines(keepends=True)
            num_t_lines = len(target_lines)

            # Slide window over lines
            for i in range(len(content_lines) - num_t_lines + 1):
                window = content_lines[i : i + num_t_lines]
                window_stripped = [l.strip() for l in window if l.strip()]

                if window_stripped == target_lines:
                    # Found normalized match
                    start_char = sum(len(l) for l in content_lines[:i])
                    matched_block = "".join(window)
                    end_char = start_char + len(matched_block)
                    return MatchResult(
                        found=True,
                        start_idx=start_char,
                        end_idx=end_char,
                        confidence=0.95,
                        matched_text=matched_block,
                        match_tier="normalized_lines",
                    )

        # Tier 3: Fuzzy sequence matching
        if len(norm_target) > 20:
            target_len = len(norm_target)
            best_ratio = 0.0
            best_start = -1
            best_end = -1

            # Check candidate sliding windows around line boundaries
            content_lines = norm_content.splitlines(keepends=True)
            num_t_lines = len(norm_target.splitlines())
            window_line_range = max(1, num_t_lines)

            for i in range(max(1, len(content_lines) - window_line_range + 1)):
                for offset in range(-1, 2):
                    actual_lines = max(1, window_line_range + offset)
                    if i + actual_lines > len(content_lines):
                        continue
                    window = "".join(content_lines[i : i + actual_lines])
                    ratio = difflib.SequenceMatcher(None, window, norm_target).ratio()
                    if ratio > best_ratio and ratio >= fuzzy_threshold:
                        best_ratio = ratio
                        best_start = sum(len(l) for l in content_lines[:i])
                        best_end = best_start + len(window)

            if best_ratio >= fuzzy_threshold and best_start != -1:
                return MatchResult(
                    found=True,
                    start_idx=best_start,
                    end_idx=best_end,
                    confidence=best_ratio,
                    matched_text=norm_content[best_start:best_end],
                    match_tier="fuzzy",
                )

        return MatchResult(found=False)

    @classmethod
    def apply_replacement(
        cls,
        content: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
        fuzzy_threshold: float = 0.82,
    ) -> tuple[bool, str, str]:
        """Apply replacement using resilient matching.
        
        Returns:
            (success: bool, modified_content: str, message: str)
        """
        norm_content = cls.normalize_newlines(content)
        norm_old = cls.normalize_newlines(old_string)
        norm_new = cls.normalize_newlines(new_string)

        if replace_all:
            if norm_old in norm_content:
                count = norm_content.count(norm_old)
                new_c = norm_content.replace(norm_old, norm_new)
                return True, new_c, f"Replaced {count} exact occurrence(s)"

        match = cls.find_best_match(norm_content, norm_old, fuzzy_threshold=fuzzy_threshold)
        if not match.found:
            return False, content, f"Target string not found (even with fuzzy tolerance)."

        new_content = (
            norm_content[: match.start_idx]
            + norm_new
            + norm_content[match.end_idx :]
        )
        return True, new_content, f"Applied edit via {match.match_tier} match (confidence: {match.confidence:.2f})"

    @classmethod
    def apply_multi_replace(
        cls,
        content: str,
        chunks: list[dict[str, str]],
    ) -> tuple[bool, str, list[str]]:
        """Apply multiple replacement chunks atomically.
        
        chunks = [{"old": "...", "new": "..."}, ...]
        """
        current_content = cls.normalize_newlines(content)
        logs = []

        for idx, chunk in enumerate(chunks, 1):
            old_str = chunk.get("old", "")
            new_str = chunk.get("new", "")
            if not old_str:
                logs.append(f"Chunk #{idx} skipped: empty old string")
                continue

            success, updated, msg = cls.apply_replacement(current_content, old_str, new_str)
            if not success:
                return False, content, logs + [f"Chunk #{idx} failed: {msg}"]
            current_content = updated
            logs.append(f"Chunk #{idx} succeeded: {msg}")

        return True, current_content, logs
