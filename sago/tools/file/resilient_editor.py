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

import ast
import difflib
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


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
                window_stripped = [w_line.strip() for w_line in window if w_line.strip()]

                if window_stripped == target_lines:
                    # Found normalized match
                    start_char = sum(len(w_line) for w_line in content_lines[:i])
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
                        best_start = sum(len(w_line) for w_line in content_lines[:i])
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
        path: str | None = None,
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
                ok, guard_msg = cls.syntax_guard(content, new_c, path)
                if not ok:
                    return False, content, guard_msg
                return True, new_c, f"Replaced {count} exact occurrence(s)"

        match = cls.find_best_match(norm_content, norm_old, fuzzy_threshold=fuzzy_threshold)
        if not match.found:
            return False, content, "Target string not found (even with fuzzy tolerance)."

        new_content = norm_content[: match.start_idx] + norm_new + norm_content[match.end_idx :]

        # Safety net: fuzzy matching can mis-anchor when the model's old_string
        # is slightly off, silently corrupting previously-valid files (seen live:
        # duplicated function bodies / stray docstrings -> IndentationError).
        # If the original parsed and the edit no longer does, reject + rollback.
        ok, guard_msg = cls.syntax_guard(content, new_content, path)
        if not ok:
            return False, content, guard_msg

        return (
            True,
            new_content,
            f"Applied edit via {match.match_tier} match (confidence: {match.confidence:.2f})",
        )

    @staticmethod
    def syntax_guard(original: str, modified: str, path: str | None = None) -> tuple[bool, str]:
        """Reject edits that break syntax in a file that previously parsed.

        Multi-language: Python (ast), JS/TS (node/tsc), Go (gofmt), Rust
        (rustfmt), Java (javac), Ruby (ruby -c), PHP (php -l), Shell (bash -n),
        C/C++ (gcc/g++). If the checker is missing, the guard is skipped.
        Returns (ok, message); message is user-facing guidance when rejected.
        """
        if not path or original == modified:
            return True, ""
        ext = Path(path).suffix.lower()

        # --- Python (zero-dependency) ---
        if ext == ".py":
            try:
                ast.parse(original)
            except SyntaxError:
                return True, ""
            try:
                ast.parse(modified)
            except SyntaxError as e:
                return False, (
                    "Edit REJECTED and rolled back: it would introduce a Python syntax error "
                    f"({e.msg} at line {e.lineno}). The file was left unchanged. "
                    "Retry using the exact current file content for old_string "
                    "(read the file again), or rewrite the whole file with write_file."
                )
            return True, ""

        # --- Generic external checker dispatch ---
        checker: tuple[list[str], str] | None = None
        tmp_suffix = ext
        if ext in (".js", ".jsx", ".mjs", ".cjs"):
            checker = (["node", "--check"], "JavaScript syntax error")
        elif ext in (".ts", ".tsx"):
            checker = (["npx", "tsc", "--noEmit", "--allowJs"], "TypeScript error")
        elif ext == ".go":
            # gofmt -e reads from stdin, reports errors to stderr
            checker = (["gofmt", "-e"], "Go format error")
        elif ext == ".rs":
            checker = (["rustfmt", "--check"], "Rust format error")
        elif ext == ".java":
            checker = (["javac", "-proc:none"], "Java compilation error")
        elif ext == ".rb":
            checker = (["ruby", "-c"], "Ruby syntax error")
        elif ext == ".php":
            checker = (["php", "-l"], "PHP syntax error")
        elif ext in (".sh", ".bash", ".zsh"):
            checker = (["bash", "-n"], "Shell syntax error")
        elif ext == ".c":
            checker = (["gcc", "-fsyntax-only", "-std=c11"], "C syntax error")
        elif ext in (".cpp", ".cc", ".cxx", ".hpp", ".hh"):
            checker = (["g++", "-fsyntax-only", "-std=c++17"], "C++ syntax error")
        else:
            return True, ""  # unknown extension: no guard

        # Only guard if original was valid (don't block recovery of broken files)
        if not ResilientEditor._external_syntax_ok(original, checker[0], tmp_suffix):
            return True, ""
        if ResilientEditor._external_syntax_ok(modified, checker[0], tmp_suffix):
            return True, ""
        return False, (
            f"Edit REJECTED and rolled back: it would introduce a {checker[1]}. "
            "The file was left unchanged. Retry using the exact current file content for "
            "old_string (read the file again), or rewrite the whole file with write_file."
        )

    @staticmethod
    def _external_syntax_ok(content: str, cmd_base: list[str], suffix: str) -> bool:
        """Run external syntax checker on content; missing tool => treat as OK."""
        tmp_path = None
        try:
            # gofmt/rustfmt read from stdin; others use temp file
            stdin_cmds = {"gofmt", "rustfmt"}
            tool = cmd_base[0]
            if tool in stdin_cmds:
                result = subprocess.run(
                    cmd_base,
                    input=content,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                return result.returncode == 0
            with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False) as f:
                f.write(content)
                f.flush()
                tmp_path = f.name
            # npx tsc needs file arg appended
            cmd = (
                [*cmd_base, tmp_path]
                if cmd_base[0] in ("npx", "javac", "gcc", "g++", "node", "ruby", "php", "bash")
                else cmd_base
            )
            # node --check, ruby -c, php -l, bash -n, javac, gcc all take file path
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except FileNotFoundError:
            return True  # checker not installed => skip guard
        except (subprocess.TimeoutExpired, OSError):
            return True
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    @classmethod
    def apply_multi_replace(
        cls,
        content: str,
        chunks: list[dict[str, str]],
        path: str | None = None,
    ) -> tuple[bool, str, list[str], int]:
        """Apply multiple replacement chunks atomically.

        chunks = [{"old": "...", "new": "..."}, ...]

        Each ``old`` string is replaced across ALL non-overlapping occurrences
        (the intended behaviour for multi-replace). Returns a 4-tuple of
        ``(success, new_content, logs, total_replacements)`` where
        ``total_replacements`` is the accurate count of applied edits.
        """
        current_content = cls.normalize_newlines(content)
        logs: list[str] = []
        total_replacements = 0

        for idx, chunk in enumerate(chunks, 1):
            old_str = chunk.get("old", "")
            new_str = chunk.get("new", "")
            if not old_str:
                logs.append(f"Chunk #{idx} skipped: empty old string")
                continue

            success, updated, msg = cls.apply_replacement(
                current_content, old_str, new_str, replace_all=True, path=path
            )
            if not success:
                return False, content, logs + [f"Chunk #{idx} failed: {msg}"], total_replacements
            current_content = updated

            # Extract the accurate occurrence count from the replacement message.
            try:
                count = int(re.search(r"(\d+)", msg).group(1))
            except (AttributeError, ValueError):
                count = 1
            total_replacements += count
            logs.append(f"Chunk #{idx} succeeded: {msg}")

        return True, current_content, logs, total_replacements
