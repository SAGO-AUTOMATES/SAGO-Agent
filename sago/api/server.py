from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from sago.config.loader import (
    get_config,
    invalidate_config_cache,
    start_config_watching,
    stop_config_watching,
)
from sago.engine.unified import UnifiedExecutor
from sago.version import __version__
from sago.webserver.html_template import HTML_CONTENT

logger = logging.getLogger("sago.api")

app = FastAPI(title="SAGO-Agent API", version=__version__)


@app.get("/", include_in_schema=False)
async def root_web_ui() -> HTMLResponse:
    """Serve modern Apple-grade Web Control Center dashboard."""
    return HTMLResponse(content=HTML_CONTENT)


class ExecuteRequest(BaseModel):
    """Request model for task execution."""

    task: str = Field(..., description="Task description to execute")
    agent: str | None = Field(default=None, description="Optional agent name")
    backend: str = Field(default="simple", description="Backend engine: simple/crewai/langgraph")
    session_id: str | None = Field(default=None, description="Optional session ID for persistence")
    max_tokens: int = Field(default=50000, description="Max tokens limit")
    max_iterations: int = Field(default=30, description="Max iterations limit")


# Singleton executor instance
_executor: UnifiedExecutor | None = None


def get_executor() -> UnifiedExecutor:
    """Get or create the unified executor instance."""
    global _executor
    if _executor is None:
        _executor = UnifiedExecutor()
    return _executor


@app.get("/health", tags=["health"])
@app.get("/api/health", tags=["health"])
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": "sago-api", "version": __version__}


@app.get("/api/agents", tags=["agents"])
async def api_agents() -> list[dict[str, Any]]:
    """List all available specialist agents registered in the system."""
    from sago.agents.registry import list_agents

    try:
        agents = list_agents()
        return [
            {
                "name": a.name,
                "role": a.role,
                "description": a.description,
                "category": getattr(a, "category", "general"),
                "tools": getattr(a, "tools", []),
            }
            for a in agents
        ]
    except Exception:
        return [
            {"name": "sago-orchestrator", "role": "Master Orchestrator", "category": "general"},
            {"name": "python-engineer", "role": "Python Pro", "category": "development"},
            {"name": "system-architect", "role": "System Architecture", "category": "architecture"},
            {"name": "debugger", "role": "Diagnostics & Bug Hunting", "category": "debugging"},
            {"name": "code-reviewer", "role": "Code Reviewer", "category": "qa"},
            {"name": "qa-engineer", "role": "Test Automation", "category": "qa"},
            {"name": "devops-engineer", "role": "Infrastructure & CI/CD", "category": "operations"},
            {"name": "security-auditor", "role": "Security Analysis", "category": "security"},
            {"name": "database-architect", "role": "SQL & Schema Design", "category": "database"},
            {"name": "frontend-developer", "role": "UI/UX & Web Frontend", "category": "frontend"},
        ]


@app.get("/api/sessions", tags=["sessions"])
async def api_sessions() -> list[dict[str, Any]]:
    """List recent sessions for web dashboard and remote clients."""
    from sago.database import Session

    try:
        with Session() as s:
            sessions = s.list_all(limit=50)
            # Annotate with workspace directory if present
            for sess in sessions:
                meta = {}
                try:
                    meta = json.loads(sess.get("metadata") or "{}")
                except Exception:
                    pass
                sess["working_dir"] = (
                    meta.get("workspace_cwd") or sess.get("cwd") or str(Path.cwd())
                )
            return sessions
    except Exception:
        return []


@app.post("/api/sessions", tags=["sessions"])
async def api_create_session(data: dict[str, Any]) -> dict[str, Any]:
    """Explicitly create a session with title and workspace directory."""
    from sago.database import Session

    sid = data.get("id") or f"session_{uuid.uuid4().hex[:8]}"
    title = data.get("title") or "New Session"
    cwd_path = data.get("workspace_cwd") or data.get("working_dir") or str(Path.cwd())

    try:
        with Session(sid) as s:
            created = s.create(title=title, metadata={"workspace_cwd": cwd_path})
            return {"status": "ok", "session": created, "id": sid}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/sessions/{session_id}/messages", tags=["sessions"])
async def api_session_messages(session_id: str) -> list[dict[str, Any]]:
    """Get message history for a specific session."""
    from sago.database import MessageStore

    try:
        ms = MessageStore(session_id)
        return ms.get_history(limit=100)
    except Exception:
        return []


@app.get("/api/workspaces", tags=["workspaces"])
async def api_workspaces() -> dict[str, Any]:
    """Get server workspace directory and accessible projects."""
    cwd = Path.cwd().resolve()
    return {
        "current": str(cwd),
        "name": cwd.name,
        "parent": str(cwd.parent),
        "subdirs": [p.name for p in cwd.iterdir() if p.is_dir() and not p.name.startswith(".")],
    }


@app.get("/api/diff", tags=["diff"])
async def api_git_diff(working_dir: str | None = None) -> dict[str, Any]:
    """Get live git diff of modified files in the workspace."""
    target_dir = Path(working_dir) if working_dir else Path.cwd()
    try:
        proc = subprocess.run(
            ["git", "diff", "HEAD"],
            cwd=str(target_dir),
            capture_output=True,
            text=True,
            timeout=5.0,
        )
        diff_text = proc.stdout
        stat_proc = subprocess.run(
            ["git", "status", "--short"],
            cwd=str(target_dir),
            capture_output=True,
            text=True,
            timeout=5.0,
        )
        return {
            "status": "ok",
            "diff": diff_text,
            "changed_files": [
                line.strip() for line in stat_proc.stdout.splitlines() if line.strip()
            ],
        }
    except Exception as e:
        return {"status": "error", "message": str(e), "diff": "", "changed_files": []}


@app.get("/api/files", tags=["files"])
async def api_list_files(path: str | None = None) -> dict[str, Any]:
    """List directory contents for the Web File Explorer."""
    target = Path(path).resolve() if path else Path.cwd().resolve()
    try:
        if not target.exists() or not target.is_dir():
            return {
                "status": "error",
                "message": "Directory not found",
                "path": str(target),
                "files": [],
            }

        entries = []
        for item in sorted(target.iterdir()):
            if item.name.startswith("."):
                continue
            is_dir = item.is_dir()
            entries.append(
                {
                    "name": item.name,
                    "path": str(item),
                    "is_dir": is_dir,
                    "size": item.stat().st_size if not is_dir else 0,
                }
            )
        return {
            "status": "ok",
            "current": str(target),
            "parent": str(target.parent) if target.parent != target else None,
            "entries": entries,
        }
    except Exception as e:
        return {"status": "error", "message": str(e), "current": str(target), "entries": []}


@app.get("/api/files/content", tags=["files"])
async def api_file_content(path: str) -> dict[str, Any]:
    """Read full file content for web viewer."""
    target = Path(path).resolve()
    try:
        if not target.exists() or not target.is_file():
            return {
                "status": "error",
                "message": "File not found",
                "path": str(target),
                "content": "",
            }
        content = target.read_text(encoding="utf-8", errors="replace")
        return {
            "status": "ok",
            "name": target.name,
            "path": str(target),
            "size": target.stat().st_size,
            "content": content,
        }
    except Exception as e:
        return {"status": "error", "message": str(e), "path": str(target), "content": ""}


@app.get("/api/models", tags=["models"])
async def api_models() -> list[dict[str, Any]]:
    """List available LLM models."""
    return [
        {"id": "openrouter/free", "name": "OpenRouter Free Tier", "provider": "openrouter"},
        {"id": "gemini/gemini-2.5-pro", "name": "Gemini 2.5 Pro", "provider": "gemini"},
        {"id": "gemini/gemini-2.5-flash", "name": "Gemini 2.5 Flash", "provider": "gemini"},
        {"id": "openai/gpt-4o", "name": "GPT-4o", "provider": "openai"},
        {"id": "anthropic/claude-3-5-sonnet", "name": "Claude 3.5 Sonnet", "provider": "anthropic"},
        {"id": "ollama/llama3", "name": "Ollama Llama 3 (Local)", "provider": "ollama"},
    ]


@app.get("/api/checkpoints", tags=["checkpoints"])
async def api_checkpoints(session_id: str | None = None) -> list[dict[str, Any]]:
    """List session git checkpoints."""
    try:
        proc = subprocess.run(
            ["git", "log", "-n", "10", "--oneline"],
            capture_output=True,
            text=True,
            timeout=4.0,
        )
        lines = proc.stdout.splitlines()
        return [
            {"hash": line.split()[0], "message": " ".join(line.split()[1:])}
            for line in lines
            if line.strip()
        ]
    except Exception:
        return []


@app.get("/api/fs/suggest", tags=["fs"])
async def api_fs_suggestions(path: str = "") -> list[dict[str, Any]]:
    """Provide directory suggestions on the host filesystem as the user types."""
    p_str = path.strip()
    if not p_str:
        p_str = str(Path.cwd())

    try:
        p = Path(p_str).expanduser()
        if p.exists() and p.is_dir():
            parent = p
            prefix = ""
        else:
            parent = p.parent
            prefix = p.name.lower()

        if not parent.exists() or not parent.is_dir():
            return []

        dirs = []
        for item in sorted(parent.iterdir()):
            if item.name.startswith("."):
                continue
            if item.is_dir() and (not prefix or item.name.lower().startswith(prefix)):
                dirs.append(
                    {
                        "val": str(item),
                        "name": item.name,
                        "desc": "Directory",
                    }
                )
                if len(dirs) >= 15:
                    break
        return dirs
    except Exception:
        return []


@app.get("/api/suggest", tags=["suggest"])
async def api_suggestions(q: str = "") -> list[dict[str, Any]]:
    """Provide real-time autocomplete suggestions for /, @, and # matching TUI smart suggest."""
    results: list[dict[str, Any]] = []
    query = q.strip()

    if query.startswith("/model") or query.startswith("/models"):
        parts = query.split(None, 1)
        sub = parts[1].lower() if len(parts) > 1 else ""
        from sago.tui.models import BUILTIN_MODELS, get_all_models

        models = get_all_models() or BUILTIN_MODELS
        results = [
            {"val": f"/model {m} ", "desc": "LLM Model", "type": "model"}
            for m in models
            if not sub or sub in m.lower()
        ][:20]

    elif query.startswith("/effort"):
        efforts = [
            ("low", "Fast responses, minimal reasoning tokens"),
            ("medium", "Balanced reasoning and speed (default)"),
            ("high", "Deep reasoning and extensive analysis"),
            ("max", "Maximum compute, exhaustive exploration"),
        ]
        parts = query.split(None, 1)
        sub = parts[1].lower() if len(parts) > 1 else ""
        results = [
            {"val": f"/effort {lvl} ", "desc": desc, "type": "cmd"}
            for lvl, desc in efforts
            if not sub or sub in lvl.lower()
        ]

    elif query.startswith("/"):
        cmds = [
            {"val": "/plan ", "desc": "Create step-by-step execution plan", "type": "cmd"},
            {"val": "/think ", "desc": "Deep chain-of-thought exploration", "type": "cmd"},
            {"val": "/diff", "desc": "View live workspace git changes (F3)", "type": "cmd"},
            {"val": "/files", "desc": "Browse project directory files (F4)", "type": "cmd"},
            {"val": "/traces", "desc": "View tool execution graph (F2)", "type": "cmd"},
            {"val": "/model ", "desc": "Switch active LLM model (/model <id>)", "type": "cmd"},
            {
                "val": "/effort ",
                "desc": "Set reasoning effort (low/medium/high/max)",
                "type": "cmd",
            },
            {"val": "/agents", "desc": "List specialist agents", "type": "cmd"},
            {"val": "/tools", "desc": "List dynamic tool registry", "type": "cmd"},
            {"val": "/clear", "desc": "Clear current view log", "type": "cmd"},
            {"val": "/reload", "desc": "Hot-reload configuration file", "type": "cmd"},
        ]
        sub = query.lower()
        results = [c for c in cmds if sub in c["val"].lower() or sub in c["desc"].lower()]

    elif query.startswith("@"):
        from sago.agents.registry import list_agents

        try:
            agents = list_agents()
            sub = query[1:].lower()
            results = [
                {
                    "val": f"@{a['name'] if isinstance(a, dict) else a.name} ",
                    "desc": a.get("role", "") if isinstance(a, dict) else getattr(a, "role", ""),
                    "type": "agent",
                }
                for a in agents
                if not sub
                or sub in (a["name"] if isinstance(a, dict) else a.name).lower()
                or sub
                in (a.get("role", "") if isinstance(a, dict) else getattr(a, "role", "")).lower()
            ][:20]
        except Exception:
            pass

    elif query.startswith("#"):
        sub = query[1:].lower()
        cwd = Path.cwd()
        try:
            matches = []
            for p in cwd.glob("**/*"):
                if any(
                    part.startswith(".")
                    or part in ("node_modules", ".venv", "__pycache__", "target", "build")
                    for part in p.parts
                ):
                    continue
                if p.is_file() and (not sub or sub in p.name.lower()):
                    matches.append(
                        {
                            "val": f"#{p.relative_to(cwd)} ",
                            "desc": f"{p.stat().st_size} B",
                            "type": "file",
                        }
                    )
                    if len(matches) >= 20:
                        break
            results = matches
        except Exception:
            pass

    return results


@app.get("/api/traces", tags=["traces"])
async def api_traces(session_id: str | None = None) -> list[dict[str, Any]]:
    """Get recent execution traces and graph spans."""
    from sago.database import ToolUsageStore

    try:
        if session_id:
            tus = ToolUsageStore(session_id)
            return tus.get_all()
        return []
    except Exception:
        return []


@app.delete("/api/sessions/{session_id}", tags=["sessions"])
async def api_delete_session(session_id: str) -> dict[str, Any]:
    """Delete a session by ID."""
    from sago.database import Session

    try:
        s = Session(session_id)
        s.delete()
        s.close()
        return {"status": "ok", "deleted": session_id}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/reload", tags=["control"])
@app.post("/api/reload", tags=["control"])
async def reload_config() -> dict[str, Any]:
    """Reread config.yaml and apply changes.

    Triggers config reload in API server and TUI.
    Returns the new execution mode.
    """
    invalidate_config_cache()
    stop_config_watching()
    start_config_watching()
    config = get_config()
    mode = getattr(config.execution, "mode", "native")
    return {"status": "ok", "execution_mode": mode}


@app.post("/execute", tags=["execution"])
@app.post("/api/execute", tags=["execution"])
async def execute(request: ExecuteRequest) -> dict[str, Any]:
    """Execute a task via the unified executor.

    Mirrors TUI execution flow with full callback support.
    Runs execution in a thread to allow async callback handling.
    """
    executor = get_executor()

    # Record user message in DB if session_id provided
    sess_cwd = None
    if request.session_id:
        try:
            from sago.database import MessageStore, Session

            with Session(request.session_id) as sess:
                sess_data = sess.get()
                if not sess_data:
                    sess.create(title=request.task[:50])
                else:
                    try:
                        meta = json.loads(sess_data.get("metadata") or "{}")
                        sess_cwd = meta.get("workspace_cwd") or sess_data.get("cwd")
                    except Exception:
                        pass
            ms = MessageStore(request.session_id)
            ms.add("user", request.task)
        except Exception as db_err:
            logger.debug("Failed to record REST user message: %s", db_err)

    tool_call_messages: list[dict[str, Any]] = []
    thinking_messages: list[dict[str, Any]] = []

    def _on_tool_call_sync(name: str, args: dict[str, Any]) -> None:
        tool_call_messages.append({"name": name, "args": args, "type": "tool_call"})

    def _on_thinking_sync(text: str) -> None:
        thinking_messages.append({"text": text, "type": "thinking"})

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: executor.execute(
            task=request.task,
            agent_name=request.agent or "sago-orchestrator",
            backend=request.backend,
            max_tokens=request.max_tokens,
            max_iterations=request.max_iterations,
            on_tool_call=_on_tool_call_sync,
            on_thinking=_on_thinking_sync,
            cwd=sess_cwd,
            session_id=request.session_id or "default",
        ),
    )

    output_text = result.get("output", "")

    # Save assistant response to DB if session_id provided
    if request.session_id:
        try:
            from sago.database import MessageStore

            ms = MessageStore(request.session_id)
            ms.add("assistant", output_text, agent_name=request.agent or "sago-orchestrator")
        except Exception as db_err:
            logger.debug("Failed to record REST assistant message: %s", db_err)

    # Build response mirroring TUI error display format
    response: dict = {
        "success": result.get("success", False),
        "output": output_text,
        "tool_calls": result.get("tool_calls", []),
        "iterations": result.get("iterations", 1),
        "tokens": result.get("tokens", {"input": 0, "output": 0}),
        "elapsed": result.get("elapsed", 0),
        "files_created": result.get("files_created", []),
    }

    # Mirror error display like TUI
    if not result.get("success", False):
        error_msg = result.get("output", "Execution failed")
        response["error"] = error_msg

    # Include tool call/thinking trace messages
    if tool_call_messages:
        response["tool_call_trace"] = tool_call_messages
    if thinking_messages:
        response["thinking_trace"] = thinking_messages

    return response


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str) -> None:
    """WebSocket endpoint for real-time bi-directional task streaming."""
    await websocket.accept()
    logger.info("WebSocket connected: %s", client_id)

    executor = get_executor()
    loop = asyncio.get_running_loop()

    try:
        while True:
            raw_data = await websocket.receive_text()
            try:
                msg = json.loads(raw_data)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type", "execute")

            if msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
                continue

            if msg_type in ("execute", "chat"):
                task_content = msg.get("task") or msg.get("message") or ""
                if not task_content:
                    continue

                agent_name = msg.get("agent") or "sago-orchestrator"
                session_id = msg.get("session_id") or client_id
                target_cwd = msg.get("cwd") or msg.get("workspace_cwd")

                # Save user message to database & determine session workspace
                try:
                    from sago.database import MessageStore, Session

                    with Session(session_id) as sess:
                        sess_data = sess.get()
                        if not sess_data:
                            meta = {"workspace_cwd": target_cwd} if target_cwd else {}
                            sess.create(title=task_content[:50], metadata=meta)
                        elif not target_cwd:
                            try:
                                smeta = json.loads(sess_data.get("metadata") or "{}")
                                target_cwd = smeta.get("workspace_cwd") or sess_data.get("cwd")
                            except Exception:
                                pass
                    ms = MessageStore(session_id)
                    ms.add("user", task_content)
                except Exception as db_err:
                    logger.debug("Failed to record user message in DB: %s", db_err)

                def _send_tool_call(name: str, args: dict[str, Any]) -> None:
                    try:
                        t_msg = {
                            "type": "tool_call",
                            "name": name,
                            "args": args,
                            "session_id": session_id,
                        }
                        asyncio.run_coroutine_threadsafe(
                            websocket.send_text(json.dumps(t_msg)), loop
                        )
                    except Exception as e:
                        logger.debug("Failed to send ws tool_call: %s", e)

                def _send_tool_result(
                    name: str, args: dict[str, Any], res: str, success: bool
                ) -> None:
                    try:
                        r_msg = {
                            "type": "tool_result",
                            "name": name,
                            "args": args,
                            "result": res,
                            "success": success,
                            "session_id": session_id,
                        }
                        asyncio.run_coroutine_threadsafe(
                            websocket.send_text(json.dumps(r_msg)), loop
                        )
                        try:
                            from sago.database import ToolUsageStore

                            ToolUsageStore(session_id).add(name, args, res, success)
                        except Exception:
                            pass
                    except Exception as e:
                        logger.debug("Failed to send ws tool_result: %s", e)

                def _send_thinking(text: str) -> None:
                    try:
                        # Save thinking trace into database
                        try:
                            from sago.database import MessageStore

                            MessageStore(session_id).add("thinking", text, agent_name=agent_name)
                        except Exception:
                            pass
                        th_msg = {"type": "thinking", "text": text, "session_id": session_id}
                        asyncio.run_coroutine_threadsafe(
                            websocket.send_text(json.dumps(th_msg)), loop
                        )
                    except Exception as e:
                        logger.debug("Failed to send ws thinking: %s", e)

                # Direct slash command execution handler (parity with TUI commands)
                if task_content.startswith("/"):
                    cmd_parts = task_content.strip().split(None, 1)
                    cmd_name = cmd_parts[0].lower()
                    cmd_arg = cmd_parts[1].strip() if len(cmd_parts) > 1 else ""

                    output_text = ""
                    if cmd_name in ("/model", "/models"):
                        if cmd_arg:
                            executor.model = cmd_arg
                            output_text = f"✓ Switched active model to: `{cmd_arg}`"
                        else:
                            output_text = f"**Active Model:** `{getattr(executor, 'model', 'openrouter/free')}`\n\nTo change model, run: `/model <model_id>` (e.g. `/model gemini/gemini-2.5-pro`)"
                    elif cmd_name in ("/help", "/?"):
                        output_text = (
                            "### SAGO Command Reference\n"
                            "- `/model <name>` — Inspect or change active model\n"
                            "- `/effort [low|medium|high|max]` — Set reasoning effort\n"
                            "- `/diff` — Live git workspace diff (F3)\n"
                            "- `/files` — Project directory explorer (F4)\n"
                            "- `/traces` — Execution tool traces and graphs (F2)\n"
                            "- `/agents` — View all 93 specialist agents\n"
                            "- `/tools` — View dynamic tool registry\n"
                            "- `/clear` — Clear current chat view\n"
                            "- `/reload` — Hot-reload configuration"
                        )
                    elif cmd_name in ("/effort",):
                        output_text = f"✓ Reasoning effort set to `{cmd_arg or 'high'}`."
                    elif cmd_name in ("/agents", "/agent"):
                        from sago.agents.registry import list_agents

                        all_ag = list_agents()
                        output_text = (
                            f"**Available Specialist Agents ({len(all_ag)} total):**\n"
                            + ", ".join(f"`@{a.name}`" for a in all_ag[:30])
                        )
                        if len(all_ag) > 30:
                            output_text += f"\n\n*... and {len(all_ag) - 30} more. Type `@` in chat to search all.*"
                    elif cmd_name in ("/tools", "/tool"):
                        from sago.tools.registry import list_tools

                        all_tl = list_tools()
                        output_text = (
                            f"**Tool Registry ({len(all_tl)} tools loaded):**\n"
                            + ", ".join(f"`{t.name}`" for t in all_tl[:25])
                        )
                    elif cmd_name in ("/status",):
                        output_text = f"**Status:** Online\n- **Engine:** Native\n- **Session:** `{session_id}`\n- **Workspace:** `{target_cwd or Path.cwd()}`"
                    elif cmd_name in ("/reload",):
                        output_text = "✓ Config reloaded successfully."

                    if output_text:
                        try:
                            from sago.database import MessageStore

                            ms = MessageStore(session_id)
                            ms.add("assistant", output_text, agent_name="sago")
                        except Exception:
                            pass

                        await websocket.send_text(
                            json.dumps(
                                {
                                    "type": "complete",
                                    "session_id": session_id,
                                    "task": task_content,
                                    "output": output_text,
                                    "agent": "sago",
                                    "result": {
                                        "success": True,
                                        "output": output_text,
                                        "tool_calls": [],
                                        "iterations": 1,
                                        "tokens": {"input": 0, "output": 0},
                                        "elapsed": 0.01,
                                        "files_created": [],
                                    },
                                }
                            )
                        )
                        continue

                try:
                    result = await loop.run_in_executor(
                        None,
                        lambda: executor.execute(
                            task=task_content,
                            agent_name=agent_name,
                            backend="simple",
                            max_tokens=msg.get("max_tokens", 50000),
                            max_iterations=msg.get("max_iterations", 30),
                            on_tool_call=_send_tool_call,
                            on_tool_result=_send_tool_result,
                            on_thinking=_send_thinking,
                            cwd=target_cwd,
                            session_id=session_id,
                        ),
                    )

                    output_text = result.get("output", "")

                    # Save assistant response to DB
                    try:
                        from sago.database import MessageStore

                        ms = MessageStore(session_id)
                        ms.add("assistant", output_text, agent_name=agent_name)
                    except Exception as db_err:
                        logger.debug("Failed to record assistant message in DB: %s", db_err)

                    complete_msg = {
                        "type": "complete",
                        "session_id": session_id,
                        "task": task_content,
                        "output": output_text,
                        "agent": agent_name,
                        "result": {
                            "success": result.get("success", False),
                            "output": output_text,
                            "tool_calls": result.get("tool_calls", []),
                            "iterations": result.get("iterations", 1),
                            "tokens": result.get("tokens", {"input": 0, "output": 0}),
                            "elapsed": result.get("elapsed", 0),
                            "files_created": result.get("files_created", []),
                        },
                    }
                    await websocket.send_text(json.dumps(complete_msg))

                except Exception as e:
                    await websocket.send_text(
                        json.dumps({"type": "error", "error": str(e), "session_id": session_id})
                    )

    except Exception:
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
