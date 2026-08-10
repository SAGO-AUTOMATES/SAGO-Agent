"""Sago Daemon Server

Runs Sago as a background service with TCP API endpoint
for remote task execution and peer communication.
Includes API key authentication, connection limits, and graceful shutdown.
"""

from __future__ import annotations

import hashlib
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
AUTH_FILE = Path.home() / ".sago" / "daemon.key"

# Default server config
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 7654
MAX_CONNECTIONS = 10
MAX_REQUEST_SIZE = 1_000_000  # 1MB
CLIENT_TIMEOUT = 300  # 5 minutes


class SagoDaemon:
    """Manages Sago daemon process with auth and connection limits."""

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        api_key: str | None = None,
        max_connections: int = MAX_CONNECTIONS,
    ) -> None:
        self.pid_file = PID_FILE
        self.log_file = LOG_FILE
        self.socket_file = SOCKET_FILE
        self.host = host
        self.port = port
        self._running = False
        self._api_key = api_key or self._load_or_create_api_key()
        self._max_connections = max_connections
        self._active_connections = 0
        self._start_time = 0.0

    def _load_or_create_api_key(self) -> str:
        """Load existing API key or create a new one."""
        if AUTH_FILE.exists():
            try:
                return AUTH_FILE.read_text().strip()
            except Exception:
                pass
        # Generate new key
        key = hashlib.sha256(os.urandom(32)).hexdigest()[:32]
        AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
        AUTH_FILE.write_text(key)
        # Restrict permissions
        try:
            AUTH_FILE.chmod(0o600)
        except Exception:
            pass
        return key

    def _verify_api_key(self, provided_key: str) -> bool:
        """Verify API key."""
        if not self._api_key:
            return True  # No auth required if no key set
        return provided_key == self._api_key

    def is_running(self) -> bool:
        """Check if daemon is running."""
        if not self.pid_file.exists():
            return False
        try:
            pid = int(self.pid_file.read_text().strip())
            os.kill(pid, 0)
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
        pid = os.fork()
        if pid > 0:
            print(f"Daemon started (PID: {pid})")
            print(f"API key saved to: {AUTH_FILE}")
            return True

        os.setsid()
        self._daemonize()
        return True

    def _daemonize(self) -> None:
        """Daemonize the process."""
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self.pid_file.write_text(str(os.getpid()))

        sys.stdout = open(self.log_file, "w")
        sys.stderr = sys.stdout

        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        self._run_server()

    def _run_foreground(self) -> bool:
        """Run in foreground."""
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self.pid_file.write_text(str(os.getpid()))

        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        print(f"Sago daemon running on {self.host}:{self.port}")
        print(f"API key: {self._api_key[:8]}...")
        print("Ctrl+C to stop")
        self._run_server()
        return True

    def _run_server(self) -> None:
        """Main server loop - TCP socket with connection limits."""
        import socket

        self._running = True
        self._start_time = time.time()
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            server.bind((self.host, self.port))
            server.listen(5)
            server.settimeout(1.0)

            print(f"Listening on {self.host}:{self.port}")

            while self._running:
                try:
                    if self._active_connections >= self._max_connections:
                        print(f"Connection limit reached ({self._max_connections}), rejecting")
                        time.sleep(0.1)
                        continue

                    client, addr = server.accept()
                    self._active_connections += 1
                    print(f"Connection from {addr} ({self._active_connections}/{self._max_connections})")

                    # Handle in a simple way (not threaded for now)
                    try:
                        self._handle_client(client)
                    finally:
                        self._active_connections -= 1
                        client.close()

                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"Error: {e}")

        finally:
            server.close()
            self.pid_file.unlink(missing_ok=True)

    def _handle_client(self, client: Any) -> None:
        """Handle client connection with auth and size limits."""
        import socket

        try:
            client.settimeout(CLIENT_TIMEOUT)
            data = b""
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    break
                data += chunk
                if len(data) > MAX_REQUEST_SIZE:
                    client.send(json.dumps({"error": "Request too large"}).encode() + b"\n")
                    return
                if b"\n" in data:
                    break

            request = json.loads(data.decode().strip())

            # Verify API key
            provided_key = request.pop("api_key", "")
            if not self._verify_api_key(provided_key):
                client.send(json.dumps({"error": "Unauthorized: invalid API key"}).encode() + b"\n")
                return

            response = self._process_request(request)
            client.send((json.dumps(response) + "\n").encode())
        except json.JSONDecodeError:
            client.send(json.dumps({"error": "Invalid JSON"}).encode() + b"\n")
        except socket.timeout:
            client.send(json.dumps({"error": "Request timeout"}).encode() + b"\n")
        except Exception as e:
            try:
                client.send(json.dumps({"error": str(e)}).encode() + b"\n")
            except Exception:
                pass

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
        """Execute a task using simple executor."""
        try:
            from sago.engine.simple_executor import execute_agent_task

            api_key = os.environ.get("OPENROUTER_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
            if not api_key:
                return {"status": "failed", "error": "No API key set (OPENROUTER_API_KEY)"}

            agent_role = agent.replace("-", " ").title() if agent else "Sago Orchestrator"

            result = execute_agent_task(
                task=task,
                agent_role=agent_role,
                api_key=api_key,
                model="openrouter/free",
                max_tokens=16384,
                max_iterations=8,
            )

            return {
                "status": "completed",
                "result": result.get("output", "No output"),
                "tool_calls": len(result.get("tool_calls", [])),
                "tokens": result.get("tokens", {}),
                "elapsed": result.get("elapsed", 0),
            }
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    def _get_status(self) -> dict[str, Any]:
        """Get daemon status."""
        return {
            "pid": os.getpid(),
            "host": self.host,
            "port": self.port,
            "uptime": time.time() - self._start_time if self._start_time else 0,
            "status": "running",
            "active_connections": self._active_connections,
            "max_connections": self._max_connections,
            "api_key_set": bool(self._api_key),
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
        """Handle shutdown signal gracefully."""
        print(f"\nReceived signal {signum}, shutting down...")
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

            if not self.is_running():
                print("Daemon stopped")
                return True
            else:
                print("Force killing...")
                os.kill(pid, signal.SIGKILL)
                self.pid_file.unlink(missing_ok=True)
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

    def __init__(self, host: str = "127.0.0.1", port: int = DEFAULT_PORT, api_key: str | None = None) -> None:
        self.host = host
        self.port = port
        self.api_key = api_key or self._load_api_key()

    def _load_api_key(self) -> str:
        """Load API key from file."""
        if AUTH_FILE.exists():
            try:
                return AUTH_FILE.read_text().strip()
            except Exception:
                pass
        return ""

    def _send(self, request: dict[str, Any]) -> dict[str, Any]:
        """Send request to daemon with auth."""
        import socket

        # Add API key to request
        if self.api_key:
            request["api_key"] = self.api_key

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
