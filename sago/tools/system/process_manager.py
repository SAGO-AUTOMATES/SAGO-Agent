"""Process Manager Tool - List, monitor, and manage system processes.

Cross-platform process management.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class ProcessManagerArgs(BaseModel):
    """Arguments for ProcessManagerTool."""

    operation: Literal["list", "search", "kill", "info", "top"] = Field(description="Operation to perform")
    query: str | None = Field(default=None, description="Search query or PID")
    signal: str = Field(default="TERM", description="Signal to send (for kill)")


class ProcessManagerTool(BaseTool):
    """Tool for managing system processes."""

    name = "process_manager"
    description = "List, search, and manage system processes."
    args_model = ProcessManagerArgs

    def _run(
        self,
        operation: str,
        query: str | None = None,
        signal: str = "TERM",
        **kwargs: Any,
    ) -> str:
        """Perform a process operation.

        Args:
            operation: Operation type.
            query: Search query or PID.
            signal: Signal for kill.

        Returns:
            Operation result.
        """
        if operation == "list":
            return self._list_processes()
        elif operation == "search":
            if query is None:
                return "Error: query required for search"
            return self._search_processes(query)
        elif operation == "kill":
            if query is None:
                return "Error: PID required for kill"
            return self._kill_process(query, signal)
        elif operation == "info":
            if query is None:
                return "Error: PID required for info"
            return self._process_info(query)
        elif operation == "top":
            return self._top_processes()

        return f"Error: Unknown operation: {operation}"

    def _list_processes(self) -> str:
        """List running processes."""
        import psutil

        processes = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                info = proc.info
                processes.append(
                    f"PID: {info['pid']:>6} | CPU: {info['cpu_percent']:>5.1f}% | "
                    f"MEM: {info['memory_percent']:>5.1f}% | {info['name']}"
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return f"=== Running Processes ({len(processes)}) ===\n" + "\n".join(processes[:50])

    def _search_processes(self, query: str) -> str:
        """Search for processes by name."""
        import psutil

        matches = []
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                info = proc.info
                name = info["name"].lower()
                cmdline = " ".join(info["cmdline"] or []).lower()

                if query.lower() in name or query.lower() in cmdline:
                    matches.append(f"PID: {info['pid']} | {info['name']}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if not matches:
            return f"No processes found matching '{query}'"

        return f"=== Processes matching '{query}' ({len(matches)}) ===\n" + "\n".join(matches)

    def _kill_process(self, pid_str: str, signal: str) -> str:
        """Kill a process by PID."""
        import signal as signal_mod
        import psutil

        try:
            pid = int(pid_str)
        except ValueError:
            return f"Error: Invalid PID: {pid_str}"

        try:
            proc = psutil.Process(pid)
            proc_name = proc.name()

            if signal.upper() == "KILL":
                proc.kill()
            else:
                proc.terminate()

            return f"Sent {signal} to process {pid} ({proc_name})"

        except psutil.NoSuchProcess:
            return f"Error: Process {pid} not found"
        except psutil.AccessDenied:
            return f"Error: Access denied to kill process {pid}"

    def _process_info(self, pid_str: str) -> str:
        """Get detailed process information."""
        import psutil

        try:
            pid = int(pid_str)
        except ValueError:
            return f"Error: Invalid PID: {pid_str}"

        try:
            proc = psutil.Process(pid)
            info = proc.as_dict(attrs=[
                "pid", "name", "status", "cpu_percent", "memory_percent",
                "create_time", "cmdline", "cwd", "username",
            ])

            lines = [f"=== Process {pid} ==="]
            lines.append(f"Name: {info['name']}")
            lines.append(f"Status: {info['status']}")
            lines.append(f"CPU: {info['cpu_percent']}%")
            lines.append(f"Memory: {info['memory_percent']:.1f}%")
            lines.append(f"User: {info.get('username', 'N/A')}")
            lines.append(f"CWD: {info.get('cwd', 'N/A')}")
            lines.append(f"Command: {' '.join(info.get('cmdline') or [])}")

            return "\n".join(lines)

        except psutil.NoSuchProcess:
            return f"Error: Process {pid} not found"

    def _top_processes(self) -> str:
        """Get top processes by CPU and memory."""
        import psutil

        processes = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                processes.append(proc.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Sort by CPU
        by_cpu = sorted(processes, key=lambda x: x["cpu_percent"] or 0, reverse=True)[:10]
        lines = ["=== Top by CPU ==="]
        for p in by_cpu:
            lines.append(f"  {p['pid']:>6} {p['cpu_percent']:>5.1f}% {p['name']}")

        # Sort by Memory
        by_mem = sorted(processes, key=lambda x: x["memory_percent"] or 0, reverse=True)[:10]
        lines.append("\n=== Top by Memory ===")
        for p in by_mem:
            lines.append(f"  {p['pid']:>6} {p['memory_percent']:>5.1f}% {p['name']}")

        return "\n".join(lines)
