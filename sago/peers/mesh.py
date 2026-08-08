"""Mesh Protocol

Peer discovery and inter-node communication for distributed Sago.
Enables automatic peer detection and task routing.
"""

from __future__ import annotations

import json
import socket
import time
from dataclasses import dataclass, field
from typing import Any


MESH_PORT = 7654
MESH_BROADCAST = "255.255.255.255"
DISCOVERY_TIMEOUT = 5


@dataclass
class MeshNode:
    """A node in the Sago mesh network."""
    id: str
    hostname: str
    ip_address: str
    port: int = MESH_PORT
    sago_version: str = "0.1.0"
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

    def to_json(self) -> str:
        return json.dumps({
            "type": self.type,
            "sender": self.sender,
            "receiver": self.receiver,
            "payload": self.payload,
            "timestamp": self.timestamp,
        })

    @classmethod
    def from_json(cls, data: str) -> MeshMessage:
        obj = json.loads(data)
        return cls(**obj)


class MeshNetwork:
    """Peer-to-peer mesh network for Sago nodes."""

    def __init__(self, node_id: str, port: int = MESH_PORT) -> None:
        self.node_id = node_id
        self.port = port
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
        except OSError:
            pass  # Port may be in use

    def stop(self) -> None:
        """Stop mesh listener."""
        self._running = False
        if self._socket:
            self._socket.close()

    def broadcast_discovery(self) -> None:
        """Broadcast discovery message."""
        msg = MeshMessage(
            type="discovery",
            sender=self.node_id,
            payload={"hostname": socket.gethostname()},
        )
        self._broadcast(msg.to_json())

    def send_heartbeat(self) -> None:
        """Send heartbeat to all known nodes."""
        msg = MeshMessage(
            type="heartbeat",
            sender=self.node_id,
            payload={"load": self._get_load()},
        )
        self._broadcast(msg.to_json())

    def send_task_request(
        self,
        target: str,
        task: str,
        agent: str | None = None,
    ) -> None:
        """Send task request to a specific node."""
        msg = MeshMessage(
            type="task_request",
            sender=self.node_id,
            receiver=target,
            payload={"task": task, "agent": agent},
        )
        self._unicast(target, msg.to_json())

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
        self._unicast(target, msg.to_json())

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
        except Exception:
            pass

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
        except Exception:
            pass

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

                messages.append(msg)

        except socket.timeout:
            pass
        except Exception:
            pass

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
            return None

        self.mesh.send_task_request(node.id, task, agent)

        # Wait for result (simplified)
        start = time.time()
        while time.time() - start < 30:
            messages = self.mesh.process_messages()
            for msg in messages:
                if msg.type == "task_result" and msg.sender == node.id:
                    return node.id, msg.payload.get("result", "")
            time.sleep(0.1)

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
