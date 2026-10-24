import json
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from sago.api.server import app


def test_api_health():
    client = TestClient(app)
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"

    res_api = client.get("/api/health")
    assert res_api.status_code == 200


def test_root_web_ui():
    client = TestClient(app)
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]


def test_api_agents():
    client = TestClient(app)
    res = client.get("/api/agents")
    assert res.status_code == 200
    agents = res.json()
    assert isinstance(agents, list)
    assert len(agents) > 0


def test_api_agents_fallback():
    client = TestClient(app)
    with patch("sago.agents.registry.list_agents", side_effect=Exception("DB error")):
        res = client.get("/api/agents")
        assert res.status_code == 200
        agents = res.json()
        assert len(agents) == 10
        assert agents[0]["name"] == "sago-orchestrator"


def test_api_sessions(tmp_path):
    from sago.database import init_db

    init_db()
    client = TestClient(app)
    # Create a session
    res = client.post(
        "/api/sessions", json={"title": "Test Session", "workspace_cwd": str(tmp_path)}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    sid = data["id"]

    # List sessions
    res_list = client.get("/api/sessions")
    assert res_list.status_code == 200
    sessions = res_list.json()
    assert any(s["id"] == sid for s in sessions)

    # Session messages
    res_msg = client.get(f"/api/sessions/{sid}/messages")
    assert res_msg.status_code == 200
    assert isinstance(res_msg.json(), list)

    # Delete session
    res_del = client.delete(f"/api/sessions/{sid}")
    assert res_del.status_code == 200
    assert res_del.json()["status"] == "ok"


def test_api_sessions_error_handling():
    client = TestClient(app)
    with patch("sago.database.Session", side_effect=Exception("DB failed")):
        res = client.get("/api/sessions")
        assert res.status_code == 200
        assert res.json() == []

        res_create = client.post("/api/sessions", json={})
        assert res_create.json()["status"] == "error"

        res_del = client.delete("/api/sessions/foo")
        assert res_del.json()["status"] == "error"


def test_api_workspaces():
    client = TestClient(app)
    res = client.get("/api/workspaces")
    assert res.status_code == 200
    data = res.json()
    assert "current" in data
    assert "name" in data


def test_api_git_diff(tmp_path):
    client = TestClient(app)
    res = client.get(f"/api/diff?working_dir={tmp_path}")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data


def test_api_files(tmp_path):
    client = TestClient(app)
    # Non-existent
    res = client.get(f"/api/files?path={tmp_path}/nonexistent")
    assert res.status_code == 200
    assert res.json()["status"] == "error"

    # Valid dir
    sub_file = tmp_path / "hello.txt"
    sub_file.write_text("world")
    res_valid = client.get(f"/api/files?path={tmp_path}")
    assert res_valid.status_code == 200
    data = res_valid.json()
    assert data["status"] == "ok"
    assert len(data["entries"]) == 1

    # File content
    res_content = client.get(f"/api/files/content?path={sub_file}")
    assert res_content.status_code == 200
    assert res_content.json()["content"] == "world"

    # Non-existent file content
    res_non = client.get(f"/api/files/content?path={tmp_path}/missing.txt")
    assert res_non.status_code == 200
    assert res_non.json()["status"] == "error"


def test_api_models():
    client = TestClient(app)
    res = client.get("/api/models")
    assert res.status_code == 200
    assert len(res.json()) >= 6


def test_api_checkpoints():
    client = TestClient(app)
    res = client.get("/api/checkpoints")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_api_fs_suggestions(tmp_path):
    client = TestClient(app)
    d1 = tmp_path / "alpha"
    d1.mkdir()
    d2 = tmp_path / "beta"
    d2.mkdir()

    res = client.get(f"/api/fs/suggest?path={tmp_path}")
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 2

    res_prefix = client.get(f"/api/fs/suggest?path={tmp_path}/alp")
    assert res_prefix.status_code == 200
    assert len(res_prefix.json()) == 1


def test_api_suggestions():
    client = TestClient(app)

    res_model = client.get("/api/suggest?q=/model gemini")
    assert res_model.status_code == 200
    assert len(res_model.json()) > 0

    res_effort = client.get("/api/suggest?q=/effort hi")
    assert res_effort.status_code == 200
    assert len(res_effort.json()) == 1

    res_cmd = client.get("/api/suggest?q=/pla")
    assert res_cmd.status_code == 200
    assert len(res_cmd.json()) > 0

    res_agent = client.get("/api/suggest?q=@py")
    assert res_agent.status_code == 200

    res_file = client.get("/api/suggest?q=#pyproject")
    assert res_file.status_code == 200


def test_api_traces():
    client = TestClient(app)
    res = client.get("/api/traces")
    assert res.status_code == 200
    assert res.json() == []

    res_sess = client.get("/api/traces?session_id=sess123")
    assert res_sess.status_code == 200


def test_reload_config():
    client = TestClient(app)
    res = client.post("/reload")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_execute_endpoint():
    client = TestClient(app)
    with patch("sago.api.server.get_executor") as mock_get_exec:
        mock_exec = MagicMock()
        mock_exec.execute.return_value = {
            "success": True,
            "output": "Result of task",
            "tool_calls": [{"name": "read_file", "args": {}}],
            "iterations": 1,
            "tokens": {"input": 10, "output": 20},
            "elapsed": 0.5,
            "files_created": ["test.py"],
        }
        mock_get_exec.return_value = mock_exec

        res = client.post(
            "/api/execute",
            json={
                "task": "Echo hello",
                "session_id": "test_exec_sess",
                "backend": "simple",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["output"] == "Result of task"


def test_execute_endpoint_failure():
    client = TestClient(app)
    with patch("sago.api.server.get_executor") as mock_get_exec:
        mock_exec = MagicMock()
        mock_exec.execute.return_value = {
            "success": False,
            "output": "Some error occurred",
        }
        mock_get_exec.return_value = mock_exec

        res = client.post(
            "/execute",
            json={"task": "Fail me"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is False
        assert data["error"] == "Some error occurred"


def test_websocket_slash_commands():
    client = TestClient(app)
    with client.websocket_connect("/ws/client_test") as ws:
        # Ping
        ws.send_text(json.dumps({"type": "ping"}))
        resp = json.loads(ws.receive_text())
        assert resp["type"] == "pong"

        # Slash command /model
        ws.send_text(json.dumps({"type": "execute", "task": "/model"}))
        resp = json.loads(ws.receive_text())
        assert resp["type"] == "complete"
        assert "Active Model" in resp["output"]

    with client.websocket_connect("/ws/client_test2") as ws:
        # Slash command /model switch
        ws.send_text(json.dumps({"type": "execute", "task": "/model gemini-2.5-flash"}))
        resp = json.loads(ws.receive_text())
        assert resp["type"] == "complete"
        assert "Switched active model to" in resp["output"]

    with client.websocket_connect("/ws/client_test3") as ws:
        # Slash command /help
        ws.send_text(json.dumps({"type": "execute", "task": "/help"}))
        resp = json.loads(ws.receive_text())
        assert "SAGO Command Reference" in resp["output"]

    with client.websocket_connect("/ws/client_test4") as ws:
        # Slash command /agents
        ws.send_text(json.dumps({"type": "execute", "task": "/agents"}))
        resp = json.loads(ws.receive_text())
        assert "Available Specialist Agents" in resp["output"]

    with client.websocket_connect("/ws/client_test5") as ws:
        # Slash command /tools
        ws.send_text(json.dumps({"type": "execute", "task": "/tools"}))
        resp = json.loads(ws.receive_text())
        assert "Tool Registry" in resp["output"]

    with client.websocket_connect("/ws/client_test6") as ws:
        # Slash command /status
        ws.send_text(json.dumps({"type": "execute", "task": "/status"}))
        resp = json.loads(ws.receive_text())
        assert "Status:" in resp["output"]


def test_websocket_execution_flow():
    client = TestClient(app)
    with patch("sago.api.server.get_executor") as mock_get_exec:
        mock_exec = MagicMock()

        def fake_execute(**kwargs):
            on_tool_call = kwargs.get("on_tool_call")
            on_tool_result = kwargs.get("on_tool_result")
            on_thinking = kwargs.get("on_thinking")
            if on_thinking:
                on_thinking("Thinking about solution...")
            if on_tool_call:
                on_tool_call("read_file", {"path": "main.py"})
            if on_tool_result:
                on_tool_result("read_file", {"path": "main.py"}, "file content", True)
            return {
                "success": True,
                "output": "Finished task",
                "tool_calls": [],
                "iterations": 1,
                "tokens": {"input": 5, "output": 10},
                "elapsed": 0.1,
                "files_created": [],
            }

        mock_exec.execute.side_effect = fake_execute
        mock_get_exec.return_value = mock_exec

        with client.websocket_connect("/ws/client_flow") as ws:
            ws.send_text(json.dumps({"type": "execute", "task": "Do work"}))
            # receive messages: thinking, tool_call, tool_result, complete
            msgs = []
            for _ in range(4):
                msgs.append(json.loads(ws.receive_text()))

            types = [m["type"] for m in msgs]
            assert "thinking" in types
            assert "tool_call" in types
            assert "tool_result" in types
            assert "complete" in types
