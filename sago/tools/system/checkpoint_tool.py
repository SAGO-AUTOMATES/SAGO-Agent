"""Checkpoint Tool for atomic snapshots and rollbacks."""

from __future__ import annotations

from typing import Any

from sago.engine.checkpoint import CheckpointManager
from sago.tools.base import BaseTool


class CheckpointTool(BaseTool):
    """Tool for taking workspace snapshots and rolling back changes."""

    name: str = "checkpoint_ops"
    description: str = (
        "Create atomic workspace snapshots or rollback files to a previous checkpoint."
    )

    def _run(
        self,
        action: str = "create",
        description: str = "Manual snapshot",
        checkpoint_id: str = "",
        **kwargs: Any,
    ) -> str:
        mgr = CheckpointManager()
        if action == "create":
            meta = mgr.create_checkpoint(description=description)
            return f"Checkpoint created: ID=`{meta.checkpoint_id}` ({len(meta.file_paths)} files saved) - {meta.description}"
        elif action == "list":
            checkpoints = mgr.list_checkpoints()
            if not checkpoints:
                return "No checkpoints found."
            lines = [f"Available Checkpoints ({len(checkpoints)}):"]
            for c in checkpoints[:10]:
                lines.append(f"• `{c.checkpoint_id}`: {c.description} ({len(c.file_paths)} files)")
            return "\n".join(lines)
        elif action == "restore":
            if not checkpoint_id:
                return "Error: `checkpoint_id` is required to restore."
            res = mgr.restore_checkpoint(checkpoint_id)
            if res.get("success"):
                return f"Successfully restored {res['restored_count']} files from checkpoint `{checkpoint_id}`."
            return f"Failed to restore checkpoint: {res.get('error')}"
        else:
            return f"Unknown action '{action}'. Valid actions: 'create', 'list', 'restore'."
