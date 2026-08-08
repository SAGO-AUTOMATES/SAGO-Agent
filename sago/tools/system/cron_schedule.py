"""Cron/Schedule Tool - Manage scheduled tasks."""

from __future__ import annotations

import subprocess
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


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
    description: str = (
        "Manage scheduled tasks: list, add, remove, enable, disable cron jobs."
    )
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
        try:
            if operation == "list":
                result = self._run_command("crontab -l 2>/dev/null || echo 'No crontab jobs'", timeout=10)
                if result.returncode != 0 or "no crontab" in result.stdout.lower():
                    return "No scheduled jobs found"
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
                        line for line in existing.splitlines()
                        if f"SAGOJOB:{name}" not in line
                    ]
                    existing = "\n".join(lines)

                new_crontab = f"{existing}\n{job_line}\n".strip()
                result = self._run_command(
                    f"echo '{new_crontab}' | crontab -",
                    timeout=10,
                )

                if result.returncode == 0:
                    return f"Added scheduled job:\n  Schedule: {schedule}\n  Command: {command}\n  Name: {name or 'unnamed'}"
                return f"Error adding job: {result.stderr}"

            elif operation == "remove":
                if not job_id and not name:
                    return "Error: job_id or name required"

                result = self._run_command("crontab -l 2>/dev/null", timeout=10)
                if result.returncode != 0:
                    return "No crontab to remove from"

                lines = result.stdout.splitlines()
                if name:
                    filtered = [l for l in lines if f"SAGOJOB:{name}" not in l]
                else:
                    filtered = [l for l in lines if job_id not in l]

                new_crontab = "\n".join(filtered)
                result = self._run_command(
                    f"echo '{new_crontab}' | crontab -",
                    timeout=10,
                )

                if result.returncode == 0:
                    return f"Removed job: {name or job_id}"
                return f"Error removing job: {result.stderr}"

            elif operation == "run-now":
                if not command:
                    return "Error: command required"

                result = self._run_command(command, timeout=60)
                return f"Command output:\n{result.stdout}\n{result.stderr}"

            else:
                return f"Error: Invalid operation '{operation}'. Valid: list, add, remove, run-now"

        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"


def get_tool() -> type[CronSchedule]:
    """Get the tool class."""
    return CronSchedule
