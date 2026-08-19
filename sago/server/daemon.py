"""Sago Daemon Server

Runs Sago as a background service with TCP API endpoint
for remote task execution and peer communication.
Includes API key authentication, connection limits, and graceful shutdown.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import signal
import sys
import time
from typing import Any

from sago.paths import get_sago_home
from sago.utils.safe import log_exception

logger = logging.getLogger("sago.server")

_sago_home = get_sago_home()
PID_FILE = _sago_home / "daemon.pid"
LOG_FILE = _sago_home / "daemon.log"
SOCKET_FILE = _sago_home / "sago.sock"
AUTH_FILE = _sago_home / "daemon.key"

# Default server config
DEFAULT_HOST = os.environ.get("SAGO_DAEMON_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("SAGO_DAEMON_PORT", "7654"))
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
                logger.info("Loaded existing API key from %s", AUTH_FILE)
                return AUTH_FILE.read_text().strip()
            except Exception as exc:
                logger.error("Failed to load API key from %s: %s", AUTH_FILE, exc)
        # Generate new key
        logger.info("Generating new API key")
        key = hashlib.sha256(os.urandom(32)).hexdigest()[:32]
        AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
        AUTH_FILE.write_text(key)
        # Restrict permissions
        try:
            AUTH_FILE.chmod(0o600)
        except Exception as exc:
            logger.warning("Could not set permissions on %s: %s", AUTH_FILE, exc)
        return key

    def _verify_api_key(self, provided_key: str) -> bool:
        """Verify API key using constant-time comparison to prevent timing attacks."""
        if not self._api_key:
            logger.debug("No API key configured, auth skipped")
            return True  # No auth required if no key set
        if not provided_key:
            logger.warning("Auth failed: no API key provided")
            return False
        result = hmac.compare_digest(provided_key, self._api_key)
        if not result:
            logger.warning("Auth failed: invalid API key")
        else:
            logger.debug("Auth succeeded")
        return result

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
            logger.warning("Daemon already running (PID: %s)", self.get_pid())
            print(f"Daemon already running (PID: {self.get_pid()})")
            return True

        logger.info("Starting daemon on %s:%d", self.host, self.port)
        if foreground:
            return self._run_foreground()
        return self._start_background()

    def _start_background(self) -> bool:
        """Start daemon in background."""
        sys.stdout.flush()
        sys.stderr.flush()
        pid = os.fork()
        if pid > 0:
            logger.info("Daemon forked, child PID: %d", pid)
            print(f"Daemon started (PID: {pid})")
            print(f"API key saved to: {AUTH_FILE}")
            return True

        os.setsid()
        self._daemonize()
        return True

    def _daemonize(self) -> None:
        """Daemonize the process with safe stream redirection."""
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self.pid_file.write_text(str(os.getpid()))

        # Redirect standard inputs and outputs cleanly
        devnull_fd = open(os.devnull)
        sys.stdin = devnull_fd

        self._log_fd = open(self.log_file, "a", encoding="utf-8")
        sys.stdout = self._log_fd
        sys.stderr = self._log_fd

        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        try:
            self._run_server()
        finally:
            if hasattr(self, "_log_fd") and self._log_fd and not self._log_fd.closed:
                self._log_fd.close()
            devnull_fd.close()

    def _run_foreground(self) -> bool:
        """Run in foreground."""
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self.pid_file.write_text(str(os.getpid()))

        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        logger.info("Daemon started in foreground on %s:%d", self.host, self.port)
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

            logger.info("Server listening on %s:%d", self.host, self.port)
            print(f"Listening on {self.host}:{self.port}")

            while self._running:
                try:
                    if self._active_connections >= self._max_connections:
                        try:
                            client, addr = server.accept()
                            logger.warning(
                                "Rejected connection from %s: connection limit reached (%d/%d)",
                                addr,
                                self._active_connections,
                                self._max_connections,
                            )
                            client.send(
                                json.dumps({"error": "Connection limit reached"}).encode() + b"\n"
                            )
                            client.close()
                        except (TimeoutError, OSError):
                            logger.debug("Failed to reject connection: timeout or OS error")
                        time.sleep(0.1)
                        continue

                    client, addr = server.accept()
                    self._active_connections += 1
                    logger.info(
                        "Connection from %s (active: %d/%d)",
                        addr,
                        self._active_connections,
                        self._max_connections,
                    )
                    print(
                        f"Connection from {addr} ({self._active_connections}/{self._max_connections})"
                    )

                    # Handle in a simple way (not threaded for now)
                    try:
                        self._handle_client(client)
                    finally:
                        self._active_connections -= 1
                        client.close()

                except TimeoutError:
                    continue
                except Exception as e:
                    logger.error("Server loop error: %s", e, exc_info=True)
                    print(f"Error: {e}")

        except OSError as exc:
            logger.error("Failed to bind server to %s:%d: %s", self.host, self.port, exc)
            raise
        finally:
            server.close()
            self.pid_file.unlink(missing_ok=True)
            logger.info("Server shutdown complete")

    def _handle_client(self, client: Any) -> None:
        """Handle client connection with auth and size limits."""
        request_start = time.time()

        try:
            client.settimeout(CLIENT_TIMEOUT)
            data = b""
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    break
                data += chunk
                if len(data) > MAX_REQUEST_SIZE:
                    logger.warning("Request too large (%d bytes)", len(data))
                    client.send(json.dumps({"error": "Request too large"}).encode() + b"\n")
                    return
                if b"\n" in data:
                    break

            request = json.loads(data.decode().strip())
            action = request.get("action", "unknown")
            logger.debug("Received request: action=%s", action)

            # Verify API key
            provided_key = request.pop("api_key", "")
            if not self._verify_api_key(provided_key):
                logger.warning("Auth failed for action=%s", action)
                client.send(json.dumps({"error": "Unauthorized: invalid API key"}).encode() + b"\n")
                return

            response = self._process_request(request)
            duration_ms = (time.time() - request_start) * 1000
            logger.debug(
                "Request completed: action=%s duration=%.1fms",
                action,
                duration_ms,
            )
            client.send((json.dumps(response) + "\n").encode())
        except json.JSONDecodeError as exc:
            logger.warning("Invalid JSON from client: %s", exc)
            client.send(json.dumps({"error": "Invalid JSON"}).encode() + b"\n")
        except TimeoutError:
            logger.warning("Client request timed out after %ds", CLIENT_TIMEOUT)
            client.send(json.dumps({"error": "Request timeout"}).encode() + b"\n")
        except (BrokenPipeError, ConnectionResetError):
            logger.debug("Client disconnected before response could be sent")
        except Exception as e:
            logger.error("Error handling client request: %s", e, exc_info=True)
            try:
                client.send(json.dumps({"error": str(e)}).encode() + b"\n")
            except (BrokenPipeError, ConnectionResetError, OSError):
                logger.debug("Client disconnected during error response")

    def _process_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Process API request."""
        action = request.get("action")

        if action == "ping":
            logger.debug("Handling ping request")
            return {"status": "ok", "pid": os.getpid()}

        elif action == "execute":
            task = request.get("task", "")
            agent = request.get("agent")
            logger.info("Task execution requested: agent=%s task_length=%d", agent, len(task))
            return self._execute_task(task, agent)

        elif action == "status":
            logger.debug("Handling status request")
            return self._get_status()

        elif action == "peers":
            logger.debug("Handling peers request")
            return self._get_peers()

        elif action == "stop":
            logger.info("Stop requested by client")
            self._running = False
            return {"status": "stopping"}

        logger.warning("Unknown action requested: %s", action)
        return {"error": f"Unknown action: {action}"}

    def _execute_task(self, task: str, agent: str | None = None) -> dict[str, Any]:
        """Execute a task using simple executor."""
        task_start = time.time()
        agent_role = agent.replace("-", " ").title() if agent else "Sago Orchestrator"
        logger.info("Executing task: agent=%s", agent_role)

        try:
            from sago.engine.simple_executor import execute_agent_task

            api_key = os.environ.get("OPENROUTER_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
            if not api_key:
                logger.error("No API key configured for task execution")
                return {"status": "failed", "error": "No API key set (OPENROUTER_API_KEY)"}

            try:
                from sago.config.loader import get_config

                model = get_config().llm.model or "openrouter/free"
            except Exception:
                model = "openrouter/free"

            result = execute_agent_task(
                task=task,
                agent_role=agent_role,
                api_key=api_key,
                model=model,
                max_tokens=16384,
                max_iterations=8,
            )

            elapsed = time.time() - task_start
            logger.info(
                "Task completed: agent=%s elapsed=%.2fs tokens=%s",
                agent_role,
                elapsed,
                result.get("tokens", {}),
            )

            return {
                "status": "completed",
                "result": result.get("output", "No output"),
                "tool_calls": len(result.get("tool_calls", [])),
                "tokens": result.get("tokens", {}),
                "elapsed": result.get("elapsed", 0),
            }
        except Exception as e:
            elapsed = time.time() - task_start
            logger.error(
                "Task execution failed: agent=%s elapsed=%.2fs error=%s",
                agent_role,
                elapsed,
                e,
                exc_info=True,
            )
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
        except Exception as exc:
            logger.error("Failed to fetch peers: %s", exc, exc_info=True)
            return {"peers": []}

    def _handle_signal(self, signum: int, frame: Any) -> None:
        """Handle shutdown signal gracefully."""
        logger.info("Received signal %d, initiating shutdown", signum)
        print(f"\nReceived signal {signum}, shutting down...")
        self._running = False

    def stop(self) -> bool:
        """Stop daemon."""
        if not self.is_running():
            logger.info("Daemon not running, nothing to stop")
            print("Daemon not running")
            return True

        pid = self.get_pid()
        if pid is None:
            return False

        logger.info("Stopping daemon (PID: %d)", pid)
        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(0.5)

            if not self.is_running():
                logger.info("Daemon stopped gracefully")
                print("Daemon stopped")
                return True
            else:
                logger.warning("Daemon did not stop gracefully, force killing")
                print("Force killing...")
                os.kill(pid, signal.SIGKILL)
                self.pid_file.unlink(missing_ok=True)
                return True
        except ProcessLookupError:
            logger.info("Daemon process %d already gone, cleaning up", pid)
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
        logger.info("Restarting daemon")
        self.stop()
        time.sleep(1)
        return self.start()


class SagoClient:
    """Client for communicating with daemon."""

    def __init__(
        self, host: str = "127.0.0.1", port: int = DEFAULT_PORT, api_key: str | None = None
    ) -> None:
        self.host = host
        self.port = port
        self.api_key = api_key or self._load_api_key()

    def _load_api_key(self) -> str:
        """Load API key from file."""
        if AUTH_FILE.exists():
            try:
                return AUTH_FILE.read_text().strip()
            except Exception as e:
                log_exception(e, "Failed to load API key in client")
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

            if not data:
                raise ConnectionError("Daemon returned empty response")

            response_str = data.decode().strip()
            if not response_str:
                raise ConnectionError("Daemon returned empty response")

            return json.loads(response_str)
        except json.JSONDecodeError as e:
            raise ConnectionError(f"Invalid response from daemon: {e}") from e
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
        return self._send(
            {
                "action": "execute",
                "task": task,
                "agent": agent,
            }
        )

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
