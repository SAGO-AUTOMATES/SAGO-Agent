"""Change Tracker - Track all file modifications per session with undo.

Tracks what files were created, modified, or deleted during a session,
with the ability to undo changes.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sago.paths import get_sago_home
from sago.utils.safe import log_exception

logger = logging.getLogger("sago.memory.change_tracker")


@dataclass
class FileChange:
    """A single file change."""

    path: str
    action: str  # "create", "modify", "delete"
    timestamp: float = field(default_factory=time.time)
    backup_path: str | None = None  # For undo
    content_before: str | None = None  # For modify
    content_after: str | None = None  # For modify/create
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "action": self.action,
            "timestamp": self.timestamp,
            "backup_path": self.backup_path,
            "content_before": self.content_before,
            "content_after": self.content_after,
        }


class ChangeTracker:
    """Tracks file modifications for a session."""

    # Paths to exclude from tracking (virtual filesystems and internal caches)
    _EXCLUDED_PREFIXES = ("/dev/", "/proc/", "/sys/", "/run/")
    _EXCLUDED_SUBSTRINGS = ("/.git/objects/", "/__pycache__/")
    _MAX_SESSION_BACKUPS = 50
    _MAX_SESSIONS_TO_KEEP = 10

    def __init__(self, session_id: str | None = None) -> None:
        self.session_id = session_id or "default"
        self.changes: list[FileChange] = []
        self._backup_dir = get_sago_home() / "backups" / self.session_id
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        self._load_index()
        self._auto_prune_old_sessions()

    def _auto_prune_old_sessions(self) -> None:
        """Prune older backup session directories to prevent unbounded accumulation."""
        try:
            backups_root = get_sago_home() / "backups"
            if not backups_root.exists():
                return
            session_dirs = [d for d in backups_root.iterdir() if d.is_dir()]
            if len(session_dirs) > self._MAX_SESSIONS_TO_KEEP:
                session_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                for old_dir in session_dirs[self._MAX_SESSIONS_TO_KEEP :]:
                    if old_dir != self._backup_dir:
                        try:
                            shutil.rmtree(old_dir, ignore_errors=True)
                        except Exception as e:
                            log_exception(e, "Failed to prune old backup directory")
        except Exception as e:
            log_exception(e, "Failed during backup session pruning")

    def _prune_session_backups(self) -> None:
        """Limit the number of backup files within the current session."""
        try:
            if not self._backup_dir.exists():
                return
            bak_files = [f for f in self._backup_dir.glob("*.bak") if f.is_file()]
            if len(bak_files) > self._MAX_SESSION_BACKUPS:
                bak_files.sort(key=lambda p: p.stat().st_mtime)
                to_remove = len(bak_files) - self._MAX_SESSION_BACKUPS
                for f in bak_files[:to_remove]:
                    f.unlink(missing_ok=True)
        except Exception as e:
            log_exception(e, "Failed to prune session backups")

    def _should_track(self, file_path: str) -> bool:
        """Check if a file path should be tracked cross-platform."""
        real_path = os.path.realpath(file_path)
        normalized_path = real_path.replace("\\", "/")
        for prefix in self._EXCLUDED_PREFIXES:
            if normalized_path.startswith(prefix):
                return False
        for sub in self._EXCLUDED_SUBSTRINGS:
            if sub in normalized_path:
                return False
        return True

    def track_create(self, file_path: str, content: str) -> FileChange | None:
        """Track file creation."""
        if not self._should_track(file_path):
            return None
        change = FileChange(
            path=file_path,
            action="create",
            content_after=content,
        )
        self.changes.append(change)
        self._save_index()
        return change

    def track_modify(self, file_path: str, old_content: str, new_content: str) -> FileChange | None:
        """Track file modification with backup for undo."""
        if not self._should_track(file_path):
            return None
        backup_path = None
        real_path = os.path.realpath(file_path)
        if os.path.exists(real_path):
            self._backup_dir.mkdir(parents=True, exist_ok=True)
            backup_name = f"{len(self.changes)}_{os.path.basename(file_path)}.bak"
            backup_path = str(self._backup_dir / backup_name)
            try:
                shutil.copy2(real_path, backup_path)
                self._prune_session_backups()
            except Exception:
                backup_path = None

        change = FileChange(
            path=file_path,
            action="modify",
            backup_path=backup_path,
            content_before=old_content,
            content_after=new_content,
        )
        self.changes.append(change)
        self._save_index()
        return change

    def track_delete(self, file_path: str, content: str) -> FileChange | None:
        """Track file deletion with backup for undo."""
        if not self._should_track(file_path):
            return None
        backup_path = None
        real_path = os.path.realpath(file_path)
        if os.path.exists(real_path):
            self._backup_dir.mkdir(parents=True, exist_ok=True)
            backup_name = f"{len(self.changes)}_{os.path.basename(file_path)}.bak"
            backup_path = str(self._backup_dir / backup_name)
            try:
                shutil.copy2(real_path, backup_path)
                self._prune_session_backups()
            except Exception:
                backup_path = None

        change = FileChange(
            path=file_path,
            action="delete",
            backup_path=backup_path,
            content_before=content,
        )
        self.changes.append(change)
        self._save_index()
        return change

    def undo_last(self) -> str | None:
        """Undo the last change. Returns the path that was undone."""
        if not self.changes:
            return None

        change = self.changes.pop()

        try:
            if change.action == "create":
                # Remove created file
                if os.path.exists(change.path):
                    os.remove(change.path)

            elif change.action == "modify":
                # Restore from backup or before content
                if change.backup_path and os.path.exists(change.backup_path):
                    shutil.copy2(change.backup_path, change.path)
                elif change.content_before is not None:
                    Path(change.path).write_text(change.content_before, encoding="utf-8")

            elif change.action == "delete":
                # Restore deleted file
                if change.backup_path and os.path.exists(change.backup_path):
                    shutil.copy2(change.backup_path, change.path)
                elif change.content_before is not None:
                    Path(change.path).write_text(change.content_before, encoding="utf-8")

            self._save_index()
            return change.path
        except Exception:
            self.changes.append(change)  # Re-add if undo failed
            return None

    def undo_all(self) -> int:
        """Undo all changes. Returns number of changes undone."""
        count = 0
        while self.changes:
            if self.undo_last():
                count += 1
        return count

    def get_summary(self) -> dict[str, Any]:
        """Get summary of all changes."""
        created = [c for c in self.changes if c.action == "create"]
        modified = [c for c in self.changes if c.action == "modify"]
        deleted = [c for c in self.changes if c.action == "delete"]

        return {
            "total": len(self.changes),
            "created": len(created),
            "modified": len(modified),
            "deleted": len(deleted),
            "files": list(set(c.path for c in self.changes)),
            "can_undo": len(self.changes) > 0,
        }

    def get_diff_summary(self) -> str:
        """Get a human-readable diff summary."""
        if not self.changes:
            return "No changes tracked."

        lines = []
        for change in self.changes:
            action = {"create": "+", "modify": "~", "delete": "-"}[change.action]
            lines.append(f"  [{action}] {change.path}")

        summary = self.get_summary()
        header = f"Changes: {summary['created']} created, {summary['modified']} modified, {summary['deleted']} deleted"
        return header + "\n" + "\n".join(lines)

    def _save_index(self) -> None:
        """Save change index to disk."""
        try:
            index_path = self._backup_dir / "index.json"
            data = [c.to_dict() for c in self.changes]
            index_path.write_text(json.dumps(data, indent=2))
        except Exception as e:
            log_exception(e, "Failed to save change index")

    def _load_index(self) -> None:
        """Load change index from disk."""
        try:
            index_path = self._backup_dir / "index.json"
            if index_path.exists():
                data = json.loads(index_path.read_text())
                self.changes = [FileChange(**item) for item in data]
        except Exception as e:
            log_exception(e, "Failed to load change index")


# Global change tracker
_change_tracker: ChangeTracker | None = None


def get_change_tracker(session_id: str | None = None) -> ChangeTracker:
    """Get or create the global change tracker."""
    global _change_tracker
    if _change_tracker is None or (session_id and _change_tracker.session_id != session_id):
        _change_tracker = ChangeTracker(session_id)
    return _change_tracker
