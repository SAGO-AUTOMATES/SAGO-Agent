from __future__ import annotations

from fastapi import WebSocket


class WebSocketManager:
    def __init__(self) -> None:
        self.active_connections: dict[str, set[WebSocket]] = {}

    async def connect(self, client_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        if client_id not in self.active_connections:
            self.active_connections[client_id] = set()
        self.active_connections[client_id].add(websocket)

    def disconnect(self, client_id: str, websocket: WebSocket) -> None:
        if client_id in self.active_connections:
            self.active_connections[client_id].discard(websocket)

    async def send_personal(self, client_id: str, message: str) -> None:
        if client_id in self.active_connections:
            for websocket in self.active_connections[client_id]:
                await websocket.send_text(message)

    async def broadcast(self, message: str) -> None:
        for conns in self.active_connections.values():
            for websocket in conns:
                await websocket.send_text(message)
