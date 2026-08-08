"""Distributed Peer System

Enables multiple Sago instances to connect, delegate tasks,
and aggregate results across servers.

Flow:
1. User: "debug auth issue on prod-server"
2. Main Sago detects remote server reference
3. Connects via SSH to prod-server
4. Checks if Sago is installed there
5. Delegates task to remote Sago agent
6. Remote Sago executes locally with full context
7. Results stream back to main Sago
8. Main Sago summarizes for user
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class PeerStatus(str, Enum):
    """Peer connection status."""
    UNKNOWN = "unknown"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    SAGO_INSTALLED = "sago_installed"
    SAGO_NOT_INSTALLED = "sago_not_installed"


class TaskStatus(str, Enum):
    """Remote task status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class PeerInfo:
    """Information about a remote peer."""
    hostname: str
    alias: str = ""
    ssh_user: str = "root"
    ssh_port: int = 22
    ssh_key: str | None = None
    status: PeerStatus = PeerStatus.UNKNOWN
    sago_version: str | None = None
    sago_path: str | None = None
    python_version: str | None = None
    os_info: str | None = None
    last_seen: float = 0.0
    latency_ms: float = 0.0
    tags: list[str] = field(default_factory=list)

    @property
    def ssh_target(self) -> str:
        return f"{self.ssh_user}@{self.hostname}"

    @property
    def display_name(self) -> str:
        return self.alias or self.hostname

    def to_dict(self) -> dict[str, Any]:
        return {
            "hostname": self.hostname,
            "alias": self.alias,
            "ssh_user": self.ssh_user,
            "ssh_port": self.ssh_port,
            "status": self.status.value,
            "sago_version": self.sago_version,
            "os_info": self.os_info,
            "latency_ms": round(self.latency_ms, 1),
            "tags": self.tags,
        }


@dataclass
class RemoteTask:
    """A task to execute on a remote peer."""
    id: str
    peer: PeerInfo
    task: str
    agent: str | None = None
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    result: str | None = None
    error: str | None = None
    tokens_used: int = 0

    @property
    def duration_ms(self) -> float | None:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at) * 1000
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "peer": self.peer.display_name,
            "task": self.task,
            "agent": self.agent,
            "status": self.status.value,
            "duration_ms": self.duration_ms,
            "tokens_used": self.tokens_used,
        }


class PeerManager:
    """Manages connections to remote Sago peers."""

    def __init__(self, config_path: str | Path | None = None) -> None:
        self.peers: dict[str, PeerInfo] = {}
        self.tasks: list[RemoteTask] = []
        self.config_path = Path(config_path) if config_path else Path.home() / ".sago" / "peers.json"
        self._load_config()

    def _load_config(self) -> None:
        """Load peer configuration."""
        if self.config_path.exists():
            try:
                with open(self.config_path) as f:
                    data = json.load(f)
                for peer_data in data.get("peers", []):
                    peer = PeerInfo(**peer_data)
                    self.peers[peer.hostname] = peer
            except Exception:
                pass

    def _save_config(self) -> None:
        """Save peer configuration."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "peers": [p.to_dict() for p in self.peers.values()]
        }
        with open(self.config_path, "w") as f:
            json.dump(data, f, indent=2)

    def add_peer(
        self,
        hostname: str,
        alias: str = "",
        ssh_user: str = "root",
        ssh_port: int = 22,
        ssh_key: str | None = None,
        tags: list[str] | None = None,
    ) -> PeerInfo:
        """Add a new peer."""
        peer = PeerInfo(
            hostname=hostname,
            alias=alias,
            ssh_user=ssh_user,
            ssh_port=ssh_port,
            ssh_key=ssh_key,
            tags=tags or [],
        )
        self.peers[hostname] = peer
        self._save_config()
        return peer

    def remove_peer(self, hostname: str) -> bool:
        """Remove a peer."""
        if hostname in self.peers:
            del self.peers[hostname]
            self._save_config()
            return True
        return False

    def get_peer(self, hostname: str) -> PeerInfo | None:
        """Get peer by hostname or alias."""
        # Check hostname
        if hostname in self.peers:
            return self.peers[hostname]
        # Check alias
        for peer in self.peers.values():
            if peer.alias == hostname:
                return peer
        return None

    def list_peers(self) -> list[PeerInfo]:
        """List all peers."""
        return list(self.peers.values())

    def find_peer_for_task(self, task: str) -> PeerInfo | None:
        """Find best peer for a task based on keywords."""
        task_lower = task.lower()

        # Check for explicit server references
        for peer in self.peers.values():
            if peer.hostname in task_lower or peer.alias in task_lower:
                return peer

        # Check tags
        for peer in self.peers.values():
            for tag in peer.tags:
                if tag.lower() in task_lower:
                    return peer

        # Return first connected peer with Sago
        for peer in self.peers.values():
            if peer.status == PeerStatus.SAGO_INSTALLED:
                return peer

        return None


class SSHManager:
    """Manages SSH connections to remote peers."""

    def __init__(self) -> None:
        self.connections: dict[str, Any] = {}

    def execute_command(
        self,
        peer: PeerInfo,
        command: str,
        timeout: int = 30,
    ) -> tuple[int, str, str]:
        """Execute command on remote peer via SSH."""
        ssh_cmd = [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=10",
            "-p", str(peer.ssh_port),
        ]

        if peer.ssh_key:
            ssh_cmd.extend(["-i", peer.ssh_key])

        ssh_cmd.append(peer.ssh_target)
        ssh_cmd.append(command)

        try:
            result = subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return 1, "", "SSH connection timed out"
        except Exception as e:
            return 1, "", str(e)

    def check_sago_installed(self, peer: PeerInfo) -> bool:
        """Check if Sago is installed on remote peer."""
        code, stdout, stderr = self.execute_command(
            peer,
            "which sago || python -c 'import sago; print(sago.__file__)' 2>/dev/null || echo 'NOT_FOUND'",
            timeout=10,
        )
        return "NOT_FOUND" not in stdout and code == 0

    def get_remote_info(self, peer: PeerInfo) -> dict[str, str]:
        """Get remote system information."""
        info = {}

        # OS info
        code, stdout, _ = self.execute_command(peer, "uname -a", timeout=5)
        if code == 0:
            info["os"] = stdout.strip()

        # Python version
        code, stdout, _ = self.execute_command(peer, "python3 --version", timeout=5)
        if code == 0:
            info["python"] = stdout.strip()

        # Sago version
        code, stdout, _ = self.execute_command(peer, "sago --version 2>/dev/null || echo 'NOT_INSTALLED'", timeout=5)
        if code == 0 and "NOT_INSTALLED" not in stdout:
            info["sago_version"] = stdout.strip()

        return info

    def check_connectivity(self, peer: PeerInfo) -> float:
        """Check connectivity and return latency in ms."""
        start = time.time()
        code, _, _ = self.execute_command(peer, "echo 'ping'", timeout=5)
        latency = (time.time() - start) * 1000

        if code == 0:
            return latency
        return -1


class RemoteExecutor:
    """Executes tasks on remote peers."""

    def __init__(self) -> None:
        self.ssh = SSHManager()
        self.peer_manager = PeerManager()
        self._task_counter = 0
        self.tasks: list[RemoteTask] = []

    def discover_peer(self, hostname: str) -> PeerInfo | None:
        """Discover and connect to a remote peer."""
        peer = self.peer_manager.get_peer(hostname)
        if not peer:
            # Try to add as new peer
            peer = self.peer_manager.add_peer(hostname)

        # Check connectivity
        peer.status = PeerStatus.CONNECTING
        latency = self.ssh.check_connectivity(peer)

        if latency < 0:
            peer.status = PeerStatus.ERROR
            return None

        peer.latency_ms = latency
        peer.status = PeerStatus.CONNECTED
        peer.last_seen = time.time()

        # Check Sago installation
        if self.ssh.check_sago_installed(peer):
            peer.status = PeerStatus.SAGO_INSTALLED
            info = self.ssh.get_remote_info(peer)
            peer.sago_version = info.get("sago_version")
            peer.python_version = info.get("python")
            peer.os_info = info.get("os")
        else:
            peer.status = PeerStatus.SAGO_NOT_INSTALLED

        return peer

    def execute_remote(
        self,
        peer: PeerInfo,
        task: str,
        agent: str | None = None,
        timeout: int = 300,
    ) -> RemoteTask:
        """Execute a task on a remote peer."""
        self._task_counter += 1
        task_id = f"remote-{self._task_counter}"

        remote_task = RemoteTask(
            id=task_id,
            peer=peer,
            task=task,
            agent=agent,
        )

        if peer.status != PeerStatus.SAGO_INSTALLED:
            remote_task.status = TaskStatus.FAILED
            remote_task.error = "Sago not installed on remote peer"
            return remote_task

        # Build remote command
        escaped_task = task.replace("'", "'\\''")
        cmd = f"sago smart '{escaped_task}'"
        if agent:
            cmd += f" --agent {agent}"

        # Execute
        remote_task.status = TaskStatus.RUNNING
        remote_task.started_at = time.time()

        code, stdout, stderr = self.ssh.execute_command(
            peer,
            cmd,
            timeout=timeout,
        )

        remote_task.completed_at = time.time()

        if code == 0:
            remote_task.status = TaskStatus.COMPLETED
            remote_task.result = stdout
        else:
            remote_task.status = TaskStatus.FAILED
            remote_task.error = stderr or stdout

        self.tasks.append(remote_task)
        return remote_task

    def delegate_to_best_peer(
        self,
        task: str,
        agent: str | None = None,
    ) -> RemoteTask | None:
        """Find best peer and delegate task."""
        peer = self.peer_manager.find_peer_for_task(task)
        if not peer:
            return None

        # Ensure peer is connected
        if peer.status != PeerStatus.SAGO_INSTALLED:
            peer = self.discover_peer(peer.hostname)
            if not peer or peer.status != PeerStatus.SAGO_INSTALLED:
                return None

        return self.execute_remote(peer, task, agent)

    def get_summary(self, tasks: list[RemoteTask] | None = None) -> str:
        """Get summary of remote execution."""
        tasks = tasks or self.tasks
        if not tasks:
            return "No remote tasks executed"

        completed = [t for t in tasks if t.status == TaskStatus.COMPLETED]
        failed = [t for t in tasks if t.status == TaskStatus.FAILED]

        lines = [
            f"Remote Execution Summary:",
            f"  Total: {len(tasks)}",
            f"  Completed: {len(completed)}",
            f"  Failed: {len(failed)}",
        ]

        if completed:
            total_tokens = sum(t.tokens_used for t in completed)
            avg_duration = sum(t.duration_ms or 0 for t in completed) / len(completed)
            lines.append(f"  Total tokens: {total_tokens:,}")
            lines.append(f"  Avg duration: {avg_duration:.0f}ms")

        return "\n".join(lines)


# Singleton
_executor: RemoteExecutor | None = None


def get_remote_executor() -> RemoteExecutor:
    """Get global remote executor."""
    global _executor
    if _executor is None:
        _executor = RemoteExecutor()
    return _executor
