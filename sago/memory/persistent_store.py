"""Persistent Markdown Memory Store (MEMORY.md and USER.md).

Manages dual-store long-term memory:
- MEMORY.md: Agent facts, architecture quirks, workspace notes
- USER.md: User preferences, style guidelines, and project directions

Features:
- Auto-initialization with structured starter templates and guidelines on first run
- Character budget enforcement
- Atomic disk updates
- Frozen snapshot pattern: session prompt gets an immutable snapshot at start
  while mid-session updates write immediately to disk for subsequent sessions.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sago.paths import get_sago_home

logger = logging.getLogger("sago.memory.persistent_store")

ENTRY_DELIMITER = "\n§\n"
DEFAULT_MEMORY_CHAR_LIMIT = 4000
DEFAULT_USER_CHAR_LIMIT = 2500

DEFAULT_MEMORY_TEMPLATE = (
    "# SAGO Agent Persistent Notes\n\n"
    "<!-- SAGO uses this file to store persistent architecture notes, workspace facts, and tool conventions. -->\n"
    "<!-- Each distinct note is separated by a standalone § section delimiter. -->\n"
    "Initial workspace memory initialized."
)

DEFAULT_USER_TEMPLATE = (
    "# User Preferences & Guidelines\n\n"
    "<!-- SAGO uses this file to remember your preferences (coding style, conventions, preferred packages). -->\n"
    "<!-- Each distinct preference is separated by a standalone § section delimiter. -->\n"
    "Prefer clear, maintainable, and type-annotated code."
)


class PersistentMemoryStore:
    """Manages persistent dual markdown memory stores across sessions."""

    def __init__(
        self,
        base_dir: Path | str | None = None,
        memory_limit: int = DEFAULT_MEMORY_CHAR_LIMIT,
        user_limit: int = DEFAULT_USER_CHAR_LIMIT,
        auto_init_defaults: bool = True,
    ) -> None:
        self.base_dir = Path(base_dir or get_sago_home())
        self.memory_file = self.base_dir / "MEMORY.md"
        self.user_file = self.base_dir / "USER.md"

        self.memory_limit = memory_limit
        self.user_limit = user_limit
        self.auto_init_defaults = auto_init_defaults

        self._memory_entries: list[str] = []
        self._user_entries: list[str] = []

        self._frozen_memory_snapshot: str | None = None
        self._frozen_user_snapshot: str | None = None

        self._ensure_default_files()
        self.reload()

    def _ensure_default_files(self) -> None:
        """Create starter MEMORY.md and USER.md if they do not exist."""
        if not self.auto_init_defaults:
            return

        try:
            self.base_dir.mkdir(parents=True, exist_ok=True)
            if not self.memory_file.exists():
                self.memory_file.write_text(DEFAULT_MEMORY_TEMPLATE, encoding="utf-8")
                logger.info("Initialized default MEMORY.md at %s", self.memory_file)

            if not self.user_file.exists():
                self.user_file.write_text(DEFAULT_USER_TEMPLATE, encoding="utf-8")
                logger.info("Initialized default USER.md at %s", self.user_file)
        except Exception as e:
            logger.warning("Failed to auto-create default memory files in %s: %s", self.base_dir, e)

    def reload(self) -> None:
        """Load entries from disk and freeze initial snapshots."""
        self._memory_entries = self._read_file_entries(self.memory_file)
        self._user_entries = self._read_file_entries(self.user_file)

        if self._frozen_memory_snapshot is None:
            self._frozen_memory_snapshot = self._format_snapshot(
                "Agent Persistent Notes", self._memory_entries
            )
        if self._frozen_user_snapshot is None:
            self._frozen_user_snapshot = self._format_snapshot(
                "User Profile & Preferences", self._user_entries
            )

    def _read_file_entries(self, path: Path) -> list[str]:
        if not path.exists():
            return []
        try:
            content = path.read_text(encoding="utf-8").strip()
            if not content:
                return []

            # Filter out top-level markdown headers and HTML comments when parsing note entries
            raw_entries = content.split(ENTRY_DELIMITER)
            cleaned_entries: list[str] = []
            for item in raw_entries:
                lines = [
                    line_text
                    for line_text in item.splitlines()
                    if not line_text.startswith("#") and not line_text.startswith("<!--")
                ]
                cleaned = "\n".join(lines).strip()
                if cleaned:
                    cleaned_entries.append(cleaned)

            return cleaned_entries
        except Exception as e:
            logger.warning("Failed to read memory file %s: %s", path, e)
            return []

    def _write_file_atomic(self, path: Path, entries: list[str], limit: int) -> None:
        """Enforce character budget and write atomically."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)

            # Evict oldest entries until within limit
            while entries and len(ENTRY_DELIMITER.join(entries)) > limit:
                entries.pop(0)

            content = ENTRY_DELIMITER.join(entries)
            temp_file = path.with_suffix(".tmp")
            temp_file.write_text(content, encoding="utf-8")
            temp_file.replace(path)
        except Exception as e:
            logger.error("Failed to write memory file %s: %s", path, e)

    def _format_snapshot(self, header: str, entries: list[str]) -> str:
        if not entries:
            return ""
        items = "\n".join(f"- {e}" for e in entries)
        return f"## {header}\n{items}"

    def get_frozen_memory_snapshot(self) -> str:
        """Get immutable snapshot of agent memory taken at session start."""
        return self._frozen_memory_snapshot or ""

    def get_frozen_user_snapshot(self) -> str:
        """Get immutable snapshot of user preferences taken at session start."""
        return self._frozen_user_snapshot or ""

    def add_memory(self, note: str) -> str:
        """Add an agent knowledge note to MEMORY.md."""
        note = note.strip()
        if not note:
            return "Empty note ignored."

        if note in self._memory_entries:
            return "Note already exists in memory."

        self._memory_entries.append(note)
        self._write_file_atomic(self.memory_file, self._memory_entries, self.memory_limit)
        return f"Saved note to persistent memory ({len(self._memory_entries)} total)."

    def add_user_preference(self, preference: str) -> str:
        """Add a user preference or guideline to USER.md."""
        preference = preference.strip()
        if not preference:
            return "Empty preference ignored."

        if preference in self._user_entries:
            return "Preference already recorded."

        self._user_entries.append(preference)
        self._write_file_atomic(self.user_file, self._user_entries, self.user_limit)
        return f"Saved user preference ({len(self._user_entries)} total)."

    def remove_memory(self, pattern: str) -> str:
        """Remove entries matching pattern substring."""
        pattern_lower = pattern.lower()
        kept = []
        removed = 0
        for entry in self._memory_entries:
            if pattern_lower in entry.lower():
                removed += 1
            else:
                kept.append(entry)

        if removed > 0:
            self._memory_entries = kept
            self._write_file_atomic(self.memory_file, self._memory_entries, self.memory_limit)
            return f"Removed {removed} matching note(s) from persistent memory."
        return "No matching notes found."


_global_memory_store: PersistentMemoryStore | None = None


def get_persistent_memory_store() -> PersistentMemoryStore:
    """Get the global PersistentMemoryStore singleton."""
    global _global_memory_store
    if _global_memory_store is None:
        _global_memory_store = PersistentMemoryStore()
    return _global_memory_store
