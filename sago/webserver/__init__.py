"""SAGO-Agent Webserver Module.

Provides unified API + WebSocket + HTML UI on a single port.
"""

from __future__ import annotations

from fastapi import FastAPI

from sago.webserver.models import (
    ApiKeyConfig,
    ConfigUpdate,
    ExecuteResponse,
    HealthCheck,
    ProviderConfig,
    SessionInfo,
    TaskRequest,
    TaskStatusResponse,
)
from sago.webserver.routes import router
from sago.webserver.websockets import WebSocketManager

__all__ = [
    "ApiKeyConfig",
    "ConfigUpdate",
    "ExecuteResponse",
    "HealthCheck",
    "ProviderConfig",
    "SessionInfo",
    "TaskRequest",
    "TaskStatusResponse",
    "WebSocketManager",
    "app",
    "ws_manager",
]

# FastAPI application
app = FastAPI(title="SAGO-Agent Webserver", version="0.1.13")
ws_manager = WebSocketManager()
app.include_router(router)
