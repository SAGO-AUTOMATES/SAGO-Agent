from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

from sago.webserver.html_template import HTML_CONTENT
from sago.webserver.models import (
    ExecuteResponse,
    HealthCheck,
    SessionInfo,
    TaskRequest,
)

logger = logging.getLogger("sago.webserver")

router = APIRouter(tags=["webserver"])

# Serve HTML UI at root path


@router.get("/", include_in_schema=False)
async def get_ui() -> HTMLResponse:
    return HTMLResponse(content=HTML_CONTENT)


@router.get("/api/health", response_model=HealthCheck)
async def api_health() -> HealthCheck:
    return HealthCheck(status="ok", version="0.1.13")


@router.post("/api/execute", response_model=ExecuteResponse)
async def api_execute(request: TaskRequest) -> ExecuteResponse:
    import asyncio

    from sago.config.loader import get_config
    from sago.engine.unified import UnifiedExecutor

    config = get_config()
    model = request.model or getattr(config.llm_providers, "default", "gemini") or "gemini"
    executor = UnifiedExecutor(api_key="", model=model)
    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: executor.execute(
                task=request.task,
                agent_name=request.agent or "python-engineer",
                system_prompt="",
                max_tokens=request.max_tokens or 4096,
                max_iterations=request.max_iterations or 8,
            ),
        )
        return ExecuteResponse(
            task_id=f"task_{hash(request.task) % 100000}",
            status="completed" if result.get("success", False) else "failed",
            message=result.get("output", "Task execution finished"),
            result=result,
        )
    except Exception as e:
        return ExecuteResponse(task_id="", status="error", message=str(e))


@router.get("/api/sessions", response_model=list[SessionInfo])
async def api_sessions() -> list[SessionInfo]:
    from sago.database import Session

    try:
        with Session() as session:
            all_sessions = session.list_all(limit=50)
            return [
                SessionInfo(
                    id=s["id"],
                    title=s.get("title", "Untitled"),
                    created_at=s["created_at"],
                    status=s.get("status", "active"),
                    message_count=0,
                    tool_count=0,
                )
                for s in all_sessions
            ]
    except Exception:
        return []


@router.post("/api/reload", response_model=None)
async def api_reload() -> dict[str, Any] | JSONResponse:
    from sago.config.loader import reload_config

    try:
        reload_config()
        return {"status": "ok", "message": "Configuration reloaded"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


# --- WebSocket Endpoint ---


@router.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str) -> None:
    await websocket.accept()
    from sago.webserver.websockets import WebSocketManager

    ws_manager = WebSocketManager()
    await ws_manager.connect(client_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                await handle_ws_message(client_id, msg, websocket)
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        ws_manager.disconnect(client_id, websocket)


async def handle_ws_message(client_id: str, msg: dict[str, Any], websocket: WebSocket) -> None:
    msg_type = msg.get("type")
    if msg_type == "execute":
        task = msg.get("task", "")
        agent = msg.get("agent", "python-engineer")
        from sago.config.loader import get_config
        from sago.engine.unified import UnifiedExecutor

        config = get_config()
        model = msg.get("model") or getattr(config.llm_providers, "default", "gemini") or "gemini"
        executor = UnifiedExecutor(api_key="", model=model)
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                None,
                lambda: executor.execute(
                    task=task,
                    agent_name=agent,
                    max_tokens=msg.get("max_tokens", 4096),
                    max_iterations=msg.get("max_iterations", 8),
                ),
            )
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "complete",
                        "task": task,
                        "output": result.get("output", ""),
                        "agent": agent,
                        "model": model,
                        "session_id": client_id,
                        "success": result.get("success", False),
                    }
                )
            )
        except Exception as e:
            await websocket.send_text(
                json.dumps({"type": "error", "error": str(e), "session_id": client_id})
            )
    elif msg_type == "cancel":
        task_id = msg.get("task_id")
        await websocket.send_text(json.dumps({"type": "cancelled", "task_id": task_id}))
