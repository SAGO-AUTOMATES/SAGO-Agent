"""Regex Tester Tool - Test and debug regular expressions."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class RegexTesterArgs(BaseModel):
    """Arguments for regex testing."""

    operation: str = Field(description="Operation: match, findall, replace, split, validate")
    pattern: str = Field(description="Regular expression pattern")
    text: str = Field(description="Text to test against")
    replacement: str = Field(default="", description="Replacement string for replace operation")
    flags: str = Field(
        default="", description="Regex flags: i (ignorecase), m (multiline), s (dotall)"
    )


class RegexTester(BaseTool):
    """Tool for testing and debugging regular expressions."""

    name: str = "regex_tester"
    description: str = "Test regular expressions: match, findall, replace, split, validate."
    args_model: type[BaseModel] = RegexTesterArgs

    def _run(
        self,
        operation: str,
        pattern: str,
        text: str,
        replacement: str = "",
        flags: str = "",
        **kwargs: Any,
    ) -> str:
        """Execute regex operation."""
        try:
            # Build flags
            re_flags = 0
            if "i" in flags:
                re_flags |= re.IGNORECASE
            if "m" in flags:
                re_flags |= re.MULTILINE
            if "s" in flags:
                re_flags |= re.DOTALL

            compiled = re.compile(pattern, re_flags)

            if operation == "validate":
                return f"Pattern is valid.\nFlags: {flags or 'none'}"

            elif operation == "match":
                matches = list(compiled.finditer(text))
                if not matches:
                    return f"No matches found for pattern: {pattern}"

                result_parts = [f"Found {len(matches)} match(es):\n"]
                for i, match in enumerate(matches, 1):
                    result_parts.append(
                        f"Match {i}: '{match.group()}' at position {match.start()}-{match.end()}"
                    )
                    if match.groups():
                        for j, group in enumerate(match.groups(), 1):
                            result_parts.append(f"  Group {j}: '{group}'")
                return "\n".join(result_parts)

            elif operation == "findall":
                matches = compiled.findall(text)
                if not matches:
                    return "No matches found"

                result_parts = [f"Found {len(matches)} match(es):\n"]
                for i, match in enumerate(matches[:50], 1):
                    if isinstance(match, tuple):
                        result_parts.append(f"  {i}: {match}")
                    else:
                        result_parts.append(f"  {i}: '{match}'")
                return "\n".join(result_parts)

            elif operation == "replace":
                if not replacement and replacement != "":
                    return "Error: replacement parameter required"

                new_text = compiled.sub(replacement, text)
                count = len(compiled.findall(text))
                return f"Replaced {count} occurrence(s):\n\nOriginal:\n{text[:500]}\n\nReplaced:\n{new_text[:500]}"

            elif operation == "split":
                parts = compiled.split(text)
                result_parts = [f"Split into {len(parts)} parts:\n"]
                for i, part in enumerate(parts[:50], 1):
                    result_parts.append(f"  {i}: '{part}'")
                return "\n".join(result_parts)

            else:
                return f"Error: Invalid operation '{operation}'. Valid: match, findall, replace, split, validate"

        except re.error as e:
            return f"Regex error: {e}"
        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"


def get_tool() -> type[RegexTester]:
    """Get the tool class."""
    return RegexTester
