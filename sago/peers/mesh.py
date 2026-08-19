"""Mesh Protocol

Peer discovery and inter-node communication for distributed Sago.
Enables automatic peer detection and task routing.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import socket
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from typing import Any

from sago.utils.safe import log_exception
from sago.version import __version__

logger = logging.getLogger("sago.peers.mesh")

MESH_PORT = int(os.environ.get("SAGO_MESH_PORT", "7655"))
MESH_BROADCAST = "255.255.255.255"
DISCOVERY_TIMEOUT = 5
# Max time a delegated task may run on a receiver before it is abandoned, so a
# hung task cannot freeze the receiver's entire mesh message pump.
MESH_TASK_TIMEOUT = int(os.environ.get("SAGO_MESH_TASK_TIMEOUT", "120"))


@dataclass
class MeshNode:
    """A node in the Sago mesh network."""

    id: str
    hostname: str
    ip_address: str
    port: int = MESH_PORT
    sago_version: str = field(default_factory=lambda: __version__)
    capabilities: list[str] = field(default_factory=list)
    load: float = 0.0  # 0-100%
    last_heartbeat: float = 0.0

    @property
    def is_alive(self) -> bool:
        return (time.time() - self.last_heartbeat) < 30

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "hostname": self.hostname,
            "ip_address": self.ip_address,
            "port": self.port,
            "sago_version": self.sago_version,
            "capabilities": self.capabilities,
            "load": self.load,
        }


@dataclass
class MeshMessage:
    """Message between mesh nodes."""

    type: str  # heartbeat, task_request, task_result, discovery
    sender: str
    receiver: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    signature: str | None = None

    def sign(self, secret: str) -> None:
        """Sign this message with an HMAC-SHA256 secret key."""
        if not secret:
            return
        payload_str = json.dumps(self.payload, sort_keys=True)
        raw = f"{self.type}:{self.sender}:{self.receiver or ''}:{self.timestamp}:{payload_str}"
        self.signature = hmac.new(
            secret.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    def verify(self, secret: str) -> bool:
        """Verify HMAC signature against the secret."""
        if not secret:
            return True
        if not self.signature:
            return False
        payload_str = json.dumps(self.payload, sort_keys=True)
        raw = f"{self.type}:{self.sender}:{self.receiver or ''}:{self.timestamp}:{payload_str}"
        expected = hmac.new(secret.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(self.signature, expected)

    def to_json(self) -> str:
        return json.dumps(
            {
                "type": self.type,
                "sender": self.sender,
                "receiver": self.receiver,
                "payload": self.payload,
                "timestamp": self.timestamp,
                "signature": self.signature,
            }
        )

    @classmethod
    def from_json(cls, data: str) -> MeshMessage:
        obj = json.loads(data)
        return cls(**obj)


class MeshNetwork:
    """Peer-to-peer mesh network for Sago nodes."""

    def __init__(
        self,
        node_id: str,
        port: int = MESH_PORT,
        auth_secret: str | None = None,
        task_executor: Any = None,
    ) -> None:
        self.node_id = node_id
        self.port = port
        self.auth_secret = auth_secret or os.environ.get("SAGO_MESH_SECRET", "")
        self.task_executor = task_executor
        self.nodes: dict[str, MeshNode] = {}
        self._running = False
        self._socket: socket.socket | None = None

    def start(self) -> None:
        """Start mesh listener."""
        self._running = True
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.settimeout(0.1)
        try:
            self._socket.bind(("", self.port))
            logger.info("Mesh listener started on port %s", self.port)
        except OSError as exc:
            logger.warning("Failed to bind mesh socket on port %s: %s", self.port, exc)

    def stop(self) -> None:
        """Stop mesh listener."""
        self._running = False
        if self._socket:
            self._socket.close()
            logger.info("Mesh listener stopped")

    def broadcast_discovery(self) -> None:
        """Broadcast discovery message."""
        msg = MeshMessage(
            type="discovery",
            sender=self.node_id,
            payload={"hostname": socket.gethostname()},
        )
        if self.auth_secret:
            msg.sign(self.auth_secret)
        self._broadcast(msg.to_json())
        logger.debug("Broadcast discovery from %s", self.node_id)

    def send_heartbeat(self) -> None:
        """Send heartbeat to all known nodes."""
        msg = MeshMessage(
            type="heartbeat",
            sender=self.node_id,
            payload={"load": self._get_load()},
        )
        if self.auth_secret:
            msg.sign(self.auth_secret)
        self._broadcast(msg.to_json())

    def send_task_request(
        self,
        target: str,
        task: str,
        agent: str | None = None,
        task_id: str | None = None,
    ) -> None:
        """Send task request to a specific node."""
        msg = MeshMessage(
            type="task_request",
            sender=self.node_id,
            receiver=target,
            payload={"task": task, "agent": agent, "task_id": task_id},
        )
        if self.auth_secret:
            msg.sign(self.auth_secret)
        self._unicast(target, msg.to_json())
        logger.debug("Sent task request to %s (task_id=%s)", target, task_id)

    def send_task_result(
        self,
        target: str,
        task_id: str,
        result: str,
        success: bool,
    ) -> None:
        """Send task result back to requester."""
        msg = MeshMessage(
            type="task_result",
            sender=self.node_id,
            receiver=target,
            payload={
                "task_id": task_id,
                "result": result,
                "success": success,
            },
        )
        if self.auth_secret:
            msg.sign(self.auth_secret)
        self._unicast(target, msg.to_json())
        logger.debug("Sent task result to %s (task_id=%s, success=%s)", target, task_id, success)

    def get_best_node(self, task: str | None = None) -> MeshNode | None:
        """Get best available node for a task."""
        alive_nodes = [n for n in self.nodes.values() if n.is_alive and n.id != self.node_id]
        if not alive_nodes:
            return None

        # Sort by load (lowest first)
        alive_nodes.sort(key=lambda n: n.load)
        return alive_nodes[0]

    def _broadcast(self, data: str) -> None:
        """Broadcast UDP message."""
        if not self._socket:
            return
        try:
            self._socket.sendto(
                data.encode(),
                (MESH_BROADCAST, self.port),
            )
        except Exception as e:
            log_exception(e, "Failed to broadcast UDP message")

    def _unicast(self, target: str, data: str) -> None:
        """Send UDP message to specific node."""
        if not self._socket:
            return
        node = self.nodes.get(target)
        if not node:
            return
        try:
            self._socket.sendto(
                data.encode(),
                (node.ip_address, node.port),
            )
        except Exception as e:
            log_exception(e, "Failed to send unicast UDP message")

    def _get_load(self) -> float:
        """Get current node load."""
        try:
            import psutil

            return psutil.cpu_percent()
        except ImportError:
            return 0.0

    def process_messages(self) -> list[MeshMessage]:
        """Process incoming mesh messages."""
        messages = []
        if not self._socket:
            return messages

        try:
            while True:
                data, addr = self._socket.recvfrom(4096)
                msg = MeshMessage.from_json(data.decode())

                if msg.sender == self.node_id:
                    continue

                # Verify HMAC signature if auth_secret is set
                if self.auth_secret and not msg.verify(self.auth_secret):
                    logger.debug("Rejected message with invalid HMAC from %s", msg.sender)
                    continue

                # Replay protection: reject packets older than 300 seconds
                if abs(time.time() - msg.timestamp) > 300:
                    logger.debug(
                        "Rejected stale message from %s (age=%.1fs)",
                        msg.sender,
                        abs(time.time() - msg.timestamp),
                    )
                    continue

                # Update node registry
                if msg.type in ("heartbeat", "discovery"):
                    node = self.nodes.get(msg.sender)
                    if node:
                        node.last_heartbeat = time.time()
                        node.load = msg.payload.get("load", 0)
                    else:
                        self.nodes[msg.sender] = MeshNode(
                            id=msg.sender,
                            hostname=msg.payload.get("hostname", msg.sender),
                            ip_address=addr[0],
                            port=addr[1],
                            last_heartbeat=time.time(),
                        )
                        logger.info("Discovered new node: %s (%s)", msg.sender, addr[0])

                # Process task requests and return execution results
                elif msg.type == "task_request" and (
                    msg.receiver == self.node_id or msg.receiver is None
                ):
                    task_str = msg.payload.get("task", "")
                    agent_name = msg.payload.get("agent")
                    task_id = msg.payload.get("task_id") or f"task_{int(time.time() * 1000)}"
                    logger.info("Received task request from %s (task_id=%s)", msg.sender, task_id)

                    def _run_task() -> str:
                        if self.task_executor:
                            out = self.task_executor(task_str, agent_name)
                            return out if isinstance(out, str) else str(out)
                        from sago.engine.simple_executor import execute_agent_task

                        res_obj = execute_agent_task(
                            task=task_str, agent_role=agent_name or "python-engineer"
                        )
                        return (
                            res_obj.get("output", "") if isinstance(res_obj, dict) else str(res_obj)
                        )

                    try:
                        with ThreadPoolExecutor(max_workers=1) as _ex:
                            fut = _ex.submit(_run_task)
                            res = fut.result(timeout=MESH_TASK_TIMEOUT)
                        self.send_task_result(
                            target=msg.sender, task_id=task_id, result=str(res), success=True
                        )
                    except FuturesTimeoutError:
                        logger.warning("Task %s timed out after %ss", task_id, MESH_TASK_TIMEOUT)
                        self.send_task_result(
                            target=msg.sender,
                            task_id=task_id,
                            result=f"Task execution timed out after {MESH_TASK_TIMEOUT}s",
                            success=False,
                        )
                    except Exception as e:  # noqa: BLE001
                        logger.error("Task %s failed: %s", task_id, e)
                        self.send_task_result(
                            target=msg.sender,
                            task_id=task_id,
                            result=f"Task execution failed: {e}",
                            success=False,
                        )

                messages.append(msg)

        except TimeoutError:
            pass
        except Exception as e:
            log_exception(e, "Unexpected error processing mesh messages")

        return messages


class MeshCoordinator:
    """Coordinates distributed task execution across mesh."""

    def __init__(self) -> None:
        self.mesh = MeshNetwork(node_id=socket.gethostname())
        self._pending_tasks: dict[str, Any] = {}

    def start(self) -> None:
        """Start mesh coordinator."""
        self.mesh.start()
        self.mesh.broadcast_discovery()
        logger.info("Mesh coordinator started (node=%s)", self.mesh.node_id)

    def stop(self) -> None:
        """Stop mesh coordinator."""
        self.mesh.stop()

    def discover_nodes(self, timeout: float = 3.0) -> list[MeshNode]:
        """Discover available nodes."""
        self.mesh.broadcast_discovery()
        time.sleep(timeout)
        return [n for n in self.mesh.nodes.values() if n.is_alive]

    def delegate_distributed(
        self,
        task: str,
        agent: str | None = None,
    ) -> tuple[str, str] | None:
        """Delegate task to best available node.

        Returns: (node_id, result) or None
        """
        node = self.mesh.get_best_node(task)
        if not node:
            logger.debug("No alive node available for delegation")
            return None

        task_id = f"task_{uuid.uuid4().hex}"
        self.mesh.send_task_request(node.id, task, agent, task_id=task_id)
        logger.info("Delegated task %s to node %s", task_id, node.id)

        # Wait for result, correlating by task_id to avoid mismatches when
        # multiple delegations target the same node concurrently.
        start = time.time()
        while time.time() - start < 30:
            messages = self.mesh.process_messages()
            for msg in messages:
                if (
                    msg.type == "task_result"
                    and msg.sender == node.id
                    and msg.payload.get("task_id") == task_id
                ):
                    return node.id, msg.payload.get("result", "")
            time.sleep(0.1)

        logger.warning("Delegation of task %s to node %s timed out", task_id, node.id)
        return None

    def get_status(self) -> dict[str, Any]:
        """Get mesh status."""
        alive = [n for n in self.mesh.nodes.values() if n.is_alive]
        return {
            "node_id": self.mesh.node_id,
            "total_nodes": len(self.mesh.nodes),
            "alive_nodes": len(alive),
            "nodes": [n.to_dict() for n in alive],
        }
