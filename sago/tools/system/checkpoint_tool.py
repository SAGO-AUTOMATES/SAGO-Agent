"""Checkpoint Tool for atomic snapshots and rollbacks."""

from __future__ import annotations

import logging
from typing import Any

from sago.engine.checkpoint import CheckpointManager
from sago.tools.base import BaseTool

logger = logging.getLogger("sago.tools.system.checkpoint_tool")


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
        logger.debug(
            "checkpoint_ops called: action=%s, description=%s, checkpoint_id=%s",
            action,
            description,
            checkpoint_id,
        )

        mgr = CheckpointManager()
        if action == "create":
            logger.info("Creating checkpoint: description=%s", description)
            meta = mgr.create_checkpoint(description=description)
            logger.info(
                "Checkpoint created: id=%s, files=%d", meta.checkpoint_id, len(meta.file_paths)
            )
            return f"Checkpoint created: ID=`{meta.checkpoint_id}` ({len(meta.file_paths)} files saved) - {meta.description}"
        elif action == "list":
            logger.info("Listing checkpoints")
            checkpoints = mgr.list_checkpoints()
            if not checkpoints:
                logger.info("No checkpoints found")
                return "No checkpoints found."
            lines = [f"Available Checkpoints ({len(checkpoints)}):"]
            for c in checkpoints[:10]:
                lines.append(f"• `{c.checkpoint_id}`: {c.description} ({len(c.file_paths)} files)")
            return "\n".join(lines)
        elif action == "restore":
            if not checkpoint_id:
                return "Error: `checkpoint_id` is required to restore."
            logger.info("Restoring checkpoint: id=%s", checkpoint_id)
            res = mgr.restore_checkpoint(checkpoint_id)
            if res.get("success"):
                logger.info(
                    "Checkpoint restored: id=%s, files=%d",
                    checkpoint_id,
                    res.get("restored_count", 0),
                )
                return f"Successfully restored {res['restored_count']} files from checkpoint `{checkpoint_id}`."
            logger.error(
                "Checkpoint restore failed: id=%s, error=%s", checkpoint_id, res.get("error")
            )
            return f"Failed to restore checkpoint: {res.get('error')}"
        else:
            logger.warning("Invalid checkpoint action: %s", action)
            return f"Unknown action '{action}'. Valid actions: 'create', 'list', 'restore'."
