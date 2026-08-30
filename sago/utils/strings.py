"""String utility helpers.

Small, dependency-free string operations used across the SAGO codebase.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

# Match one or more whitespace characters (spaces, tabs, newlines, etc.).
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_whitespace(
    text: str,
    *,
    strip: bool = True,
    keep_newlines: bool = False,
) -> str:
    """Collapse runs of whitespace into a single separator.

    Args:
        text: Input string to normalize. Must be a ``str``.
        strip: If ``True`` (default), strip leading/trailing whitespace.
        keep_newlines: If ``True``, preserve ``\\n`` as a line break and only
            collapse other whitespace. If ``False`` (default), collapse all
            whitespace including newlines into a single space.

    Returns:
        Normalized string.

    Raises:
        TypeError: If ``text`` is not a ``str``.
    """
    if not isinstance(text, str):
        raise TypeError(f"normalize_whitespace expected str, got {type(text).__name__}")

    if keep_newlines:
        # Preserve newlines, collapse other whitespace per-line.
        lines = text.split("\n")
        cleaned: list[str] = []
        for line in lines:
            collapsed = _WHITESPACE_RE.sub(" ", line)
            if strip:
                collapsed = collapsed.strip()
            cleaned.append(collapsed)
        result = "\n".join(cleaned)
        if strip:
            result = result.strip()
        return result

    result = _WHITESPACE_RE.sub(" ", text)
    if strip:
        result = result.strip()
    return result


def join_nonempty(parts: Iterable[str], separator: str = " ") -> str:
    """Join an iterable of strings, skipping empty or whitespace-only items.

    Args:
        parts: Iterable of string fragments.
        separator: String placed between joined fragments.

    Returns:
        Joined string with empty fragments removed.

    Raises:
        TypeError: If any item in ``parts`` is not a ``str``.
    """
    cleaned: list[str] = []
    for i, item in enumerate(parts):
        if not isinstance(item, str):
            raise TypeError(
                f"join_nonempty expected str at position {i}, got {type(item).__name__}"
            )
        if item.strip():
            cleaned.append(item)
    return separator.join(cleaned)


def truncate_text(
    text: str,
    max_chars: int,
    *,
    suffix: str = "...",
    break_on_word: bool = True,
) -> str:
    """Truncate ``text`` to at most ``max_chars`` characters.

    A simple, dependency-free alternative to :func:`truncate_text_by_tokens`
    for callers who only need a character-based cap (e.g. UI labels, log
    lines, table cells).

    Args:
        text: Input string to truncate.
        max_chars: Maximum length of the returned string **including** any
            appended ``suffix``. Must be non-negative.
        suffix: String appended to the result when truncation occurs. Pass
            an empty string to disable the suffix. The suffix counts toward
            ``max_chars``.
        break_on_word: If ``True`` and a space occurs in the latter half of
            the candidate window, truncate at the last space so the result
            does not end mid-word. If ``False``, perform a hard cut.

    Returns:
        The original text if it already fits within ``max_chars``; otherwise
        a truncated string whose length is at most ``max_chars`` and ends
        with ``suffix`` (when ``suffix`` is non-empty and truncation
        actually occurred).

    Raises:
        TypeError: If ``text`` is not a ``str``, ``max_chars`` is not an
            ``int``, or ``suffix`` is not a ``str``.
        ValueError: If ``max_chars`` is negative, or if ``suffix`` is longer
            than ``max_chars`` (which would make a truncated result exceed
            the requested cap).
    """
    if not isinstance(text, str):
        raise TypeError(f"truncate_text expected str, got {type(text).__name__}")
    if not isinstance(max_chars, int) or isinstance(max_chars, bool):
        raise TypeError(f"truncate_text expected int for max_chars, got {type(max_chars).__name__}")
    if not isinstance(suffix, str):
        raise TypeError(f"truncate_text expected str for suffix, got {type(suffix).__name__}")
    if max_chars < 0:
        raise ValueError(f"max_chars must be non-negative, got {max_chars}")

    # ``max_chars == 0`` means the caller wants an empty string regardless
    # of suffix; handle it before the suffix-length check to keep the API
    # forgiving and consistent with ``truncate_text_by_tokens``.
    if max_chars == 0:
        return ""

    if len(suffix) > max_chars:
        raise ValueError(f"suffix length ({len(suffix)}) must not exceed max_chars ({max_chars})")

    if len(text) <= max_chars:
        return text

    # We need room for the suffix in the final result.
    cut_at = max_chars - len(suffix)
    if cut_at <= 0:
        # Only the suffix itself fits; the caller asked for it explicitly.
        return suffix[:max_chars]

    if break_on_word:
        candidate = text[:cut_at]
        last_space = candidate.rfind(" ")
        # Only break on a word boundary if it leaves a reasonable amount
        # of content (>= 50% of the cut window) — otherwise hard cut.
        if last_space > cut_at // 2:
            return candidate[:last_space].rstrip() + suffix

    return text[:cut_at].rstrip() + suffix


# Approximate tokens-per-character ratios per model family.
_TOKEN_RATIOS: dict[str, float] = {
    "gpt-4o": 3.8,
    "gpt-4": 3.8,
    "gpt-35": 3.8,  # gpt-3.5-turbo
    "claude-3": 3.5,
    "claude-2": 3.5,
    "gemini": 2.5,
    "default": 4.0,  # conservative fallback
}


def truncate_text_by_tokens(
    text: str,
    max_tokens: int,
    *,
    model: str = "gpt-4o-mini",
) -> str:
    """Truncate ``text`` to fit within ``max_tokens`` estimated tokens.

    Uses a conservative character-to-token ratio based on the model family.
    When ``tiktoken`` is available it is used for exact counting.

    Args:
        text: Input text to truncate.
        max_tokens: Maximum number of tokens the result may occupy.
        model: Model identifier (default: ``"gpt-4o-mini"``). Used only for
            heuristic ratio lookup when tiktoken is unavailable.

    Returns:
        The input text, or the text truncated to fit within ``max_tokens``.
        Never returns a string longer than the input.

    Raises:
        TypeError: If ``text`` is not a ``str`` or ``max_tokens`` is not an ``int``.
        ValueError: If ``max_tokens`` is negative.
    """
    if not isinstance(text, str):
        raise TypeError(f"truncate_text_by_tokens expected str, got {type(text).__name__}")
    if not isinstance(max_tokens, int):
        raise TypeError(
            f"truncate_text_by_tokens expected int for max_tokens, got {type(max_tokens).__name__}"
        )
    if max_tokens < 0:
        raise ValueError(f"max_tokens must be non-negative, got {max_tokens}")

    if max_tokens == 0:
        return ""

    # Fast path: try exact count via tiktoken.
    try:
        import tiktoken  # type: ignore

        encoding = tiktoken.encoding_for_model(_tiktoken_model_name(model))
        tokens = encoding.encode(text, disallowed_special=())
        if len(tokens) <= max_tokens:
            return text
        decoded = encoding.decode(tokens[:max_tokens])
        return decoded
    except Exception:
        # tiktoken unavailable or model not recognised — fall through to heuristic.
        pass

    # Heuristic fallback: estimate using character ratio.
    ratio = _TOKEN_RATIOS.get("default")
    for key, val in _TOKEN_RATIOS.items():
        if key != "default" and key in model.lower():
            ratio = val
            break

    max_chars = int(max_tokens * ratio)  # type: ignore[arg-type]
    if len(text) <= max_chars:
        return text

    # Truncate on word boundary when possible.
    truncated = text[:max_chars]
    last_space = truncated.rfind(" ")
    if last_space > max_chars * 0.7:
        return truncated[:last_space].rstrip()
    return truncated.rstrip()


def _tiktoken_model_name(model: str) -> str:
    """Map a user-facing model name to a tiktoken model name."""
    model_lower = model.lower()
    if "gpt-4o-mini" in model_lower:
        return "gpt-4o-mini"
    if "gpt-4o" in model_lower:
        return "gpt-4o"
    if "gpt-4" in model_lower:
        return "gpt-4"
    if "gpt-3.5" in model_lower or "gpt-35" in model_lower:
        return "gpt-3.5-turbo"
    if "claude" in model_lower:
        # tiktoken doesn't support claude models; raise so callers fall back.
        raise ValueError(f"tiktoken does not support model {model!r}")
    return model


def extract_between(
    text: str,
    start: str,
    end: str,
    *,
    missing_start: str = "raise",
    missing_end: str = "raise",
) -> str:
    """Extract the substring between the first occurrence of ``start`` and ``end``.

    Useful for parsing delimited content such as XML tags, quoted strings, or
    bracketed expressions.

    Args:
        text: Input string to search within.
        start: Opening delimiter. The character or substring that marks the
            beginning of the region to extract (excluded from the result).
        end: Closing delimiter. The character or substring that marks the
            end of the region to extract (excluded from the result).
        missing_start: Behaviour when ``start`` is not found.
            - ``"raise"`` (default): raise ``ValueError``.
            - ``"return_empty"``: return an empty string.
            - ``"return_original"``: return the original ``text`` unchanged.
        missing_end: Behaviour when ``start`` is found but ``end`` is not.
            - ``"raise"`` (default): raise ``ValueError``.
            - ``"return_empty"``: return an empty string.
            - ``"return_original"``: return the original ``text`` unchanged.

    Returns:
        The substring between ``start`` and ``end``, exclusive of both delimiters.
        Returns ``""`` when ``missing_start`` or ``missing_end`` is set to
        ``"return_empty"`` and the respective delimiter is absent.

    Raises:
        TypeError: If ``text``, ``start``, or ``end`` is not a ``str``.
        ValueError: If ``start`` is not found and ``missing_start="raise"``;
            or if ``start`` is found but ``end`` is not and ``missing_end="raise"``.
    """
    if not isinstance(text, str):
        raise TypeError(f"extract_between expected str for text, got {type(text).__name__}")
    if not isinstance(start, str):
        raise TypeError(f"extract_between expected str for start, got {type(start).__name__}")
    if not isinstance(end, str):
        raise TypeError(f"extract_between expected str for end, got {type(end).__name__}")

    start_idx = text.find(start)
    if start_idx == -1:
        if missing_start == "raise":
            raise ValueError(f"Opening delimiter {start!r} not found in text")
        if missing_start == "return_original":
            return text
        return ""  # missing_start == "return_empty"

    # Position after the opening delimiter
    after_start = start_idx + len(start)
    end_idx = text.find(end, after_start)

    if end_idx == -1:
        if missing_end == "raise":
            raise ValueError(f"Closing delimiter {end!r} not found after {start!r}")
        if missing_end == "return_original":
            return text
        return ""  # missing_end == "return_empty"

    return text[after_start:end_idx]


def extract_all_between(
    text: str,
    start: str,
    end: str,
) -> list[str]:
    """Extract all substrings between ``start`` and ``end`` delimiters.

    Scans the input string from left to right, returning every region that
    lies between consecutive ``start`` / ``end`` pairs.

    Args:
        text: Input string to search within.
        start: Opening delimiter (excluded from each result).
        end: Closing delimiter (excluded from each result).

    Returns:
        List of all substrings between ``start`` and ``end`` pairs, in order.
        Returns an empty list when no complete pairs are found.

    Raises:
        TypeError: If ``text``, ``start``, or ``end`` is not a ``str``.
    """
    if not isinstance(text, str):
        raise TypeError(f"extract_all_between expected str for text, got {type(text).__name__}")
    if not isinstance(start, str):
        raise TypeError(f"extract_all_between expected str for start, got {type(start).__name__}")
    if not isinstance(end, str):
        raise TypeError(f"extract_all_between expected str for end, got {type(end).__name__}")

    results: list[str] = []
    pos = 0

    while True:
        start_idx = text.find(start, pos)
        if start_idx == -1:
            break

        after_start = start_idx + len(start)
        end_idx = text.find(end, after_start)
        if end_idx == -1:
            break

        results.append(text[after_start:end_idx])
        pos = end_idx + len(end)

    return results


# Match a run of characters that are NOT slug-safe for ASCII mode.
_SLUG_ASCII_SAFE_RE_TEMPLATE = r"[^a-z0-9{sep}]+"
# Match a run of characters that are NOT \w (and not the separator itself) for unicode mode.
_SLUG_UNICODE_SAFE_RE_TEMPLATE = r"[^\w{sep}]+"


def slugify(
    text: str,
    *,
    max_length: int = 80,
    separator: str = "-",
    allow_unicode: bool = False,
) -> str:
    """Convert ``text`` into a URL/file-system-safe slug.

    Lower-cases the input, removes characters that are not alphanumeric (or
    not a separator when ``allow_unicode=True``), and collapses runs of
    non-alphanumerics into a single ``separator``.

    Args:
        text: Input string to slugify.
        max_length: Maximum length of the returned slug. Must be ``>= 1``.
            The result is trimmed at the last separator boundary that fits,
            so the returned value is always no longer than ``max_length``.
        separator: Character used to join word boundaries (default ``"-"``).
        allow_unicode: If ``True``, preserve Unicode letters/digits; if
            ``False`` (default), restrict to ASCII ``[a-z0-9]``.

    Returns:
        A slugified, lowercase string. Returns an empty string if the input
        contains no slug-safe characters.

    Raises:
        TypeError: If ``text``, ``separator`` is not a ``str``, or
            ``max_length`` is not an ``int``.
        ValueError: If ``max_length < 1``, ``separator`` is empty, or
            ``separator`` contains characters not allowed in a slug.
    """
    if not isinstance(text, str):
        raise TypeError(f"slugify expected str, got {type(text).__name__}")
    if not isinstance(separator, str):
        raise TypeError(f"slugify expected str for separator, got {type(separator).__name__}")
    # Reject bool (which is a subclass of int in Python).
    if isinstance(max_length, bool) or not isinstance(max_length, int):
        raise TypeError(f"slugify expected int for max_length, got {type(max_length).__name__}")
    if max_length < 1:
        raise ValueError(f"max_length must be >= 1, got {max_length}")
    if not separator:
        raise ValueError("separator must be a non-empty string")

    # Validate separator.
    if allow_unicode:
        if any(ch.isspace() for ch in separator):
            raise ValueError("separator must not contain whitespace")
    else:
        if len(separator) != 1 or not (
            separator.isascii() and (separator.isalnum() or separator in {"-", "_"})
        ):
            raise ValueError(
                f"separator must be a single ASCII alphanumeric, '-', or '_', got {separator!r}"
            )

    # Optionally NFKD-normalize + strip combining marks for unicode mode.
    working = text
    if allow_unicode:
        import unicodedata

        working = unicodedata.normalize("NFKD", working)
        working = "".join(ch for ch in working if not unicodedata.combining(ch))

    working = working.casefold()

    # Build the "not safe" pattern. The separator itself is treated as
    # safe so we collapse *other* chars into the separator and then strip
    # leading/trailing separators in one pass.
    sep_escaped = re.escape(separator)
    if allow_unicode:
        pattern = re.compile(
            _SLUG_UNICODE_SAFE_RE_TEMPLATE.format(sep=sep_escaped),
            re.UNICODE,
        )
    else:
        pattern = re.compile(_SLUG_ASCII_SAFE_RE_TEMPLATE.format(sep=sep_escaped))

    cleaned = pattern.sub(separator, working).strip(separator)

    if not cleaned:
        return ""

    # Trim to max_length at the last separator boundary.
    if len(cleaned) > max_length:
        trimmed = cleaned[:max_length]
        last_sep = trimmed.rfind(separator)
        if last_sep > 0:
            trimmed = trimmed[:last_sep]
        if not trimmed:
            # No separator found in the prefix; hard-trim.
            trimmed = cleaned[:max_length]
        cleaned = trimmed

    return cleaned
