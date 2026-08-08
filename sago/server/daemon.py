"""Sago Daemon Server

Runs Sago as a background service with TCP API endpoint
for remote task execution and peer communication.
"""

from __future__ import annotations

import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any


PID_FILE = Path.home() / ".sago" / "daemon.pid"
LOG_FILE = Path.home() / ".sago" / "daemon.log"
SOCKET_FILE = Path.home() / ".sago" / "sago.sock"

# Default server config
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 7654


class SagoDaemon:
    """Manages Sago daemon process."""

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
        self.pid_file = PID_FILE
        self.log_file = LOG_FILE
        self.socket_file = SOCKET_FILE
        self.host = host
        self.port = port
        self._running = False

    def is_running(self) -> bool:
        """Check if daemon is running."""
        if not self.pid_file.exists():
            return False
        try:
            pid = int(self.pid_file.read_text().strip())
            os.kill(pid, 0)  # Check if process exists
            return True
        except (ProcessLookupError, ValueError):
            self.pid_file.unlink(missing_ok=True)
            return False

    def get_pid(self) -> int | None:
        """Get daemon PID."""
        if not self.pid_file.exists():
            return None
        try:
            return int(self.pid_file.read_text().strip())
        except ValueError:
            return None

    def start(self, foreground: bool = False) -> bool:
        """Start daemon."""
        if self.is_running():
            print(f"Daemon already running (PID: {self.get_pid()})")
            return True

        if foreground:
            return self._run_foreground()
        return self._start_background()

    def _start_background(self) -> bool:
        """Start daemon in background."""
        # Fork
        pid = os.fork()
        if pid > 0:
            # Parent
            print(f"Daemon started (PID: {pid})")
            return True

        # Child
        os.setsid()
        self._daemonize()
        return True  # Should not reach here in child

    def _daemonize(self) -> None:
        """Daemonize the process."""
        # Write PID
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self.pid_file.write_text(str(os.getpid()))

        # Redirect stdout/stderr
        sys.stdout = open(self.log_file, "w")
        sys.stderr = sys.stdout

        # Handle signals
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        # Run server
        self._run_server()

    def _run_foreground(self) -> bool:
        """Run in foreground."""
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self.pid_file.write_text(str(os.getpid()))

        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        print(f"Sago daemon running on {self.host}:{self.port} (Ctrl+C to stop)")
        self._run_server()
        return True

    def _run_server(self) -> None:
        """Main server loop - TCP socket."""
        import socket

        self._running = True
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            server.bind((self.host, self.port))
            server.listen(5)
            server.settimeout(1.0)

            print(f"Listening on {self.host}:{self.port}")

            while self._running:
                try:
                    client, addr = server.accept()
                    print(f"Connection from {addr}")
                    self._handle_client(client)
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"Error: {e}")

        finally:
            server.close()
            self.pid_file.unlink(missing_ok=True)

    def _handle_client(self, client: Any) -> None:
        """Handle client connection."""
        import socket

        try:
            data = b""
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data:
                    break

            request = json.loads(data.decode().strip())
            response = self._process_request(request)
            client.send((json.dumps(response) + "\n").encode())
        except Exception as e:
            client.send(json.dumps({"error": str(e)}).encode() + b"\n")
        finally:
            client.close()

    def _process_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Process API request."""
        action = request.get("action")

        if action == "ping":
            return {"status": "ok", "pid": os.getpid()}

        elif action == "execute":
            task = request.get("task", "")
            agent = request.get("agent")
            return self._execute_task(task, agent)

        elif action == "status":
            return self._get_status()

        elif action == "peers":
            return self._get_peers()

        elif action == "stop":
            self._running = False
            return {"status": "stopping"}

        return {"error": f"Unknown action: {action}"}

    def _execute_task(self, task: str, agent: str | None = None) -> dict[str, Any]:
        """Execute a task."""
        try:
            from sago.agents.spawner import AgentSpawner
            from sago.database import init

            init()
            spawner = AgentSpawner()

            if agent:
                result = spawner.execute_with_agent(agent, task)
            else:
                result = spawner.orchestrate(task)

            return {"status": "completed", "result": str(result)}
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    def _get_status(self) -> dict[str, Any]:
        """Get daemon status."""
        return {
            "pid": os.getpid(),
            "host": self.host,
            "port": self.port,
            "uptime": time.time(),
            "status": "running",
        }

    def _get_peers(self) -> dict[str, Any]:
        """Get peer information."""
        try:
            from sago.peers.manager import PeerManager
            pm = PeerManager()
            peers = pm.list_peers()
            return {"peers": [p.to_dict() for p in peers]}
        except Exception:
            return {"peers": []}

    def _handle_signal(self, signum: int, frame: Any) -> None:
        """Handle shutdown signal."""
        self._running = False

    def stop(self) -> bool:
        """Stop daemon."""
        if not self.is_running():
            print("Daemon not running")
            return True

        pid = self.get_pid()
        if pid is None:
            return False

        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(0.5)

            # Check if stopped
            if not self.is_running():
                print("Daemon stopped")
                return True
            else:
                print("Force killing...")
                os.kill(pid, signal.SIGKILL)
                return True
        except ProcessLookupError:
            self.pid_file.unlink(missing_ok=True)
            return True

    def status(self) -> str:
        """Get daemon status."""
        if self.is_running():
            pid = self.get_pid()
            return f"Running (PID: {pid}) on {self.host}:{self.port}"
        return "Not running"

    def restart(self) -> bool:
        """Restart daemon."""
        self.stop()
        time.sleep(1)
        return self.start()


class SagoClient:
    """Client for communicating with daemon."""

    def __init__(self, host: str = "127.0.0.1", port: int = DEFAULT_PORT) -> None:
        self.host = host
        self.port = port

    def _send(self, request: dict[str, Any]) -> dict[str, Any]:
        """Send request to daemon."""
        import socket

        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(30)
        try:
            client.connect((self.host, self.port))
            client.send((json.dumps(request) + "\n").encode())

            data = b""
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data:
                    break

            return json.loads(data.decode().strip())
        except ConnectionRefusedError:
            raise ConnectionError("Daemon not running")
        finally:
            client.close()

    def ping(self) -> bool:
        """Ping daemon."""
        try:
            response = self._send({"action": "ping"})
            return response.get("status") == "ok"
        except Exception:
            return False

    def execute(self, task: str, agent: str | None = None) -> dict[str, Any]:
        """Execute task on daemon."""
        return self._send({
            "action": "execute",
            "task": task,
            "agent": agent,
        })

    def status(self) -> dict[str, Any]:
        """Get daemon status."""
        return self._send({"action": "status"})

    def stop_daemon(self) -> dict[str, Any]:
        """Stop daemon."""
        return self._send({"action": "stop"})


def get_daemon(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> SagoDaemon:
    """Get daemon instance."""
    return SagoDaemon(host=host, port=port)


def get_client(host: str = "127.0.0.1", port: int = DEFAULT_PORT) -> SagoClient:
    """Get client instance."""
    return SagoClient(host=host, port=port)
