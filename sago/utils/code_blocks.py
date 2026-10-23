"""Language-agnostic brace/indent based code block extraction helpers.

Provides more accurate chunk boundaries than fixed line windows for C-style
languages (JS/TS/Go/Rust/Java/C/C++/C#/Kotlin/Swift/PHP) without requiring
tree-sitter. Falls back to fixed windows when braces are unbalanced.
"""

from __future__ import annotations

from collections.abc import Iterator


def brace_block_spans(lines: list[str], start_idx: int) -> tuple[int, int]:
    """Return (start, end_exclusive) line indices for a brace-delimited block
    starting at ``start_idx``. ``start_idx`` must point at a line containing '{'.
    """
    depth = 0
    seen_open = False
    for i in range(start_idx, len(lines)):
        for ch in lines[i]:
            if ch == "{":
                depth += 1
                seen_open = True
            elif ch == "}":
                depth -= 1
                if seen_open and depth == 0:
                    return start_idx, i + 1
    # Unbalanced: fall back to a modest fixed window.
    return start_idx, min(start_idx + 40, len(lines))


def iter_brace_blocks(
    content: str, header_patterns: list[tuple[str, str]]
) -> Iterator[tuple[int, int, str, str]]:
    """Yield (start_line, end_line_exclusive, name, kind) for brace blocks.

    ``header_patterns`` is a list of (regex, kind) applied to each line; the
    first match on a line wins. The header line must contain '{' or the next
    non-empty line must.
    """
    import re

    lines = content.splitlines()
    i = 0
    n = len(lines)
    while i < n:
        matched_kind = None
        matched_name = None
        for pattern, kind in header_patterns:
            m = re.search(pattern, lines[i])
            if m:
                matched_kind = kind
                matched_name = m.group(1) if m.groups() else ""
                break
        if matched_kind:
            # Find opening brace
            start = i
            brace_line = i
            while brace_line < n and "{" not in lines[brace_line]:
                brace_line += 1
                if brace_line - i > 3:
                    break
            if brace_line < n and "{" in lines[brace_line]:
                s, e = brace_block_spans(lines, brace_line)
                # Include header lines before brace
                yield (start, e, matched_name or "", matched_kind)
                i = e
                continue
        i += 1
