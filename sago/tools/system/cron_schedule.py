"""Cron/Schedule Tool - Manage scheduled tasks."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool

logger = logging.getLogger("sago.tools.system.cron_schedule")


class CronScheduleArgs(BaseModel):
    """Arguments for cron/schedule operations."""

    operation: str = Field(description="Operation: list, add, remove, enable, disable, run-now")
    schedule: str = Field(default="", description="Cron expression (e.g., '0 * * * *')")
    command: str = Field(default="", description="Command to execute")
    job_id: str = Field(default="", description="Job ID for remove/enable/disable")
    name: str = Field(default="", description="Job name for add operation")


class CronSchedule(BaseTool):
    """Tool for managing scheduled tasks (cron jobs)."""

    name: str = "cron_schedule"
    description: str = "Manage scheduled tasks: list, add, remove, enable, disable cron jobs."
    args_model: type[BaseModel] = CronScheduleArgs

    def _run(
        self,
        operation: str,
        schedule: str = "",
        command: str = "",
        job_id: str = "",
        name: str = "",
        **kwargs: Any,
    ) -> str:
        """Execute cron operation."""
        logger.debug(
            "cron_schedule called: operation=%s, schedule=%s, command=%s",
            operation,
            schedule,
            command,
        )

        try:
            if operation == "list":
                logger.info("Listing cron jobs")
                result = self._run_command(
                    "crontab -l 2>/dev/null || echo 'No crontab jobs'", timeout=10
                )
                if result.returncode != 0 or "no crontab" in result.stdout.lower():
                    logger.info("No cron jobs found")
                    return "No scheduled jobs found"
                logger.info("Found cron jobs: returncode=%d", result.returncode)
                return f"Scheduled jobs:\n{result.stdout}"

            elif operation == "add":
                if not schedule or not command:
                    return "Error: schedule and command required"

                # Add job with comment
                job_line = f"{schedule} {command} # SAGOJOB:{name or 'unnamed'}"

                # Get existing crontab and append
                result = self._run_command("crontab -l 2>/dev/null", timeout=10)
                existing = result.stdout if result.returncode == 0 else ""

                # Remove existing job with same name
                if name:
                    lines = [
                        line for line in existing.splitlines() if f"SAGOJOB:{name}" not in line
                    ]
                    existing = "\n".join(lines)

                new_crontab = f"{existing}\n{job_line}\n".strip()
                # Use a temp file approach to avoid shell injection
                import tempfile

                with tempfile.NamedTemporaryFile(mode="w", suffix=".crontab", delete=False) as f:
                    f.write(new_crontab + "\n")
                    tmpfile = f.name
                try:
                    logger.info(
                        "Adding cron job: schedule=%s, command=%s, name=%s",
                        schedule,
                        command,
                        name or "unnamed",
                    )
                    result = self._run_command(
                        f"crontab {tmpfile}",
                        timeout=10,
                    )
                finally:
                    import os

                    os.unlink(tmpfile)

                if result.returncode == 0:
                    logger.info("Cron job added successfully: name=%s", name or "unnamed")
                    return f"Added scheduled job:\n  Schedule: {schedule}\n  Command: {command}\n  Name: {name or 'unnamed'}"
                logger.error("Failed to add cron job: stderr=%s", result.stderr)
                return f"Error adding job: {result.stderr}"

            elif operation == "remove":
                if not job_id and not name:
                    return "Error: job_id or name required"

                result = self._run_command("crontab -l 2>/dev/null", timeout=10)
                if result.returncode != 0:
                    return "No crontab to remove from"

                lines = result.stdout.splitlines()
                if name:
                    filtered = [line for line in lines if f"SAGOJOB:{name}" not in line]
                else:
                    filtered = [line for line in lines if job_id not in line]

                new_crontab = "\n".join(filtered)
                # Use a temp file approach to avoid shell injection
                import tempfile

                with tempfile.NamedTemporaryFile(mode="w", suffix=".crontab", delete=False) as f:
                    f.write(new_crontab + "\n" if new_crontab else "")
                    tmpfile = f.name
                try:
                    logger.info("Removing cron job: name=%s, job_id=%s", name, job_id)
                    result = self._run_command(
                        f"crontab {tmpfile}",
                        timeout=10,
                    )
                finally:
                    import os

                    os.unlink(tmpfile)

                if result.returncode == 0:
                    logger.info("Cron job removed: %s", name or job_id)
                    return f"Removed job: {name or job_id}"
                logger.error("Failed to remove cron job: stderr=%s", result.stderr)
                return f"Error removing job: {result.stderr}"

            elif operation == "run-now":
                if not command:
                    return "Error: command required"

                logger.info("Running cron command now: %s", command)
                result = self._run_command(command, timeout=60)
                logger.info("Cron command completed: returncode=%d", result.returncode)
                return f"Command output:\n{result.stdout}\n{result.stderr}"

            else:
                logger.warning("Invalid cron_schedule operation: %s", operation)
                return f"Error: Invalid operation '{operation}'. Valid: list, add, remove, run-now"

        except Exception as e:
            logger.error("Cron schedule operation failed: operation=%s, error=%s", operation, e)
            return f"Error: {type(e).__name__}: {e}"


def get_tool() -> type[CronSchedule]:
    """Get the tool class."""
    return CronSchedule
