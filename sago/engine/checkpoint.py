"""Checkpoint & Instant Rollback System for SAGO Multi-Agent Orchestration.

Takes atomic snapshots of files before complex autonomous refactoring operations
and allows instant rollback if tests or validation fail.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CheckpointMeta:
    """Metadata for a repository snapshot."""

    checkpoint_id: str
    description: str
    timestamp: float
    file_paths: list[str]
    git_commit: str = ""
    author: str = "sago"

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "description": self.description,
            "timestamp": self.timestamp,
            "file_paths": self.file_paths,
            "git_commit": self.git_commit,
            "author": self.author,
        }


class CheckpointManager:
    """Manages workspace snapshots and rollbacks."""

    def __init__(self, workspace_root: str | Path | None = None) -> None:
        self.root = Path(workspace_root) if workspace_root else Path.cwd()
        self.checkpoints_dir = self.root / ".sago" / "checkpoints"
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)

    def create_checkpoint(
        self, description: str, files: list[str | Path] | None = None
    ) -> CheckpointMeta:
        """Create a new checkpoint snapshotting specified files (or all tracked/modified files)."""
        ts = time.time()
        chk_id = f"chk_{int(ts)}_{abs(hash(description)) % 10000:04d}"
        snap_dir = self.checkpoints_dir / chk_id
        snap_dir.mkdir(parents=True, exist_ok=True)

        copied_files: list[str] = []

        if files:
            target_files = [Path(f) if isinstance(f, str) else f for f in files]
        else:
            # Default to modified or all non-ignored project files up to 500
            target_files = []
            for ext in ("*.py", "*.ts", "*.js", "*.go", "*.rs", "*.json", "*.yaml", "*.md"):
                for p in self.root.rglob(ext):
                    if (
                        ".sago" in p.parts
                        or ".git" in p.parts
                        or ".venv" in p.parts
                        or "node_modules" in p.parts
                    ):
                        continue
                    target_files.append(p)
                    if len(target_files) >= 500:
                        break

        for fpath in target_files:
            abs_path = fpath if fpath.is_absolute() else self.root / fpath
            if not abs_path.is_file():
                continue

            try:
                rel = abs_path.relative_to(self.root)
            except ValueError:
                rel = abs_path

            dest = snap_dir / "data" / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(abs_path, dest)
            copied_files.append(str(rel))

        meta = CheckpointMeta(
            checkpoint_id=chk_id,
            description=description,
            timestamp=ts,
            file_paths=copied_files,
        )

        with open(snap_dir / "meta.json", "w", encoding="utf-8") as fp:
            json.dump(meta.to_dict(), fp, indent=2)

        logger.info(
            "Created checkpoint %s with %d files: %s", chk_id, len(copied_files), description
        )
        return meta

    def list_checkpoints(self, limit: int = 50) -> list[CheckpointMeta]:
        """List all available snapshots ordered from newest to oldest."""
        results = []
        if not self.checkpoints_dir.exists():
            return []

        for p in sorted(self.checkpoints_dir.iterdir(), reverse=True):
            if len(results) >= limit:
                break
            meta_file = p / "meta.json"
            if meta_file.is_file():
                try:
                    with open(meta_file, encoding="utf-8") as fp:
                        data = json.load(fp)
                        results.append(
                            CheckpointMeta(
                                checkpoint_id=data["checkpoint_id"],
                                description=data["description"],
                                timestamp=data["timestamp"],
                                file_paths=data.get("file_paths", []),
                                git_commit=data.get("git_commit", ""),
                                author=data.get("author", "sago"),
                            )
                        )
                except Exception as e:
                    logger.debug("Failed to read checkpoint meta %s: %s", meta_file, e)

        return results

    def restore_checkpoint(self, checkpoint_id: str) -> dict[str, Any]:
        """Restore all files from a specific snapshot."""
        snap_dir = self.checkpoints_dir / checkpoint_id
        if not snap_dir.exists():
            return {"success": False, "error": f"Checkpoint '{checkpoint_id}' not found."}

        data_dir = snap_dir / "data"

        if not data_dir.exists():
            return {"success": False, "error": f"Checkpoint data missing for '{checkpoint_id}'."}

        restored_files = []
        for p in data_dir.rglob("*"):
            if p.is_file():
                rel = p.relative_to(data_dir)
                dest = self.root / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dest)
                restored_files.append(str(rel))

        return {
            "success": True,
            "checkpoint_id": checkpoint_id,
            "restored_count": len(restored_files),
            "files": restored_files,
        }


_GLOBAL_CHECKPOINT_MGR: CheckpointManager | None = None


def get_checkpoint_manager(workspace_root: str | Path | None = None) -> CheckpointManager:
    """Get or instantiate global CheckpointManager."""
    global _GLOBAL_CHECKPOINT_MGR
    if _GLOBAL_CHECKPOINT_MGR is None or workspace_root is not None:
        _GLOBAL_CHECKPOINT_MGR = CheckpointManager(workspace_root=workspace_root)
    return _GLOBAL_CHECKPOINT_MGR
