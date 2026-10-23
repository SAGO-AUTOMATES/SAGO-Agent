"""API parity tests - comparing native TUI execution vs API/WebSocket execution."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from sago.api.server import ExecuteRequest, app
from sago.config.loader import get_config, init_user_config, invalidate_config_cache


def get_execution_mode() -> str:
    """Helper to get execution mode from config."""
    from sago.api.config import get_execution_mode

    return get_execution_mode()


@pytest.fixture(autouse=True)
def setup_config():
    """Ensure config is initialized for tests."""
    init_user_config(force=True)
    yield
    # Clean up after test
    invalidate_config_cache()


@pytest.mark.asyncio
async def test_health_endpoint():
    """Test that GET /health returns expected response."""
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "ok"
    assert data.get("service") == "sago-api"


@pytest.mark.asyncio
async def test_reload_config_endpoint():
    """Test POST /reload rereads config.yaml and returns new execution mode."""
    client = TestClient(app)

    # Get initial mode
    cfg = get_config()
    initial_mode = cfg.execution.mode
    assert initial_mode in ("native", "api")

    # Trigger reload
    resp = client.post("/reload")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "ok"
    assert "execution_mode" in data
    # Mode should be the same or changed depending on config
    assert data["execution_mode"] in ("native", "api")


@pytest.mark.asyncio
async def test_execute_endpoint_accepts_json(monkeypatch):
    """Test that /execute endpoint accepts JSON body correctly."""
    from sago.api import server

    mock_result = {
        "success": True,
        "output": "def add(a, b): return a + b",
        "tool_calls": [],
        "iterations": 1,
        "tokens": {"input": 10, "output": 15},
    }

    class DummyExecutor:
        def execute(self, **kwargs):
            return mock_result

    monkeypatch.setattr(server, "get_executor", lambda: DummyExecutor())
    client = TestClient(app)

    resp = client.post("/execute", json={"task": "Write a Python function"})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


@pytest.mark.asyncio
async def test_execute_endpoint_has_required_fields(monkeypatch):
    """Test that /execute response has expected structure when execution succeeds."""
    from sago.api import server

    mock_result = {
        "success": True,
        "output": "def add(a, b): return a + b",
        "tool_calls": [],
        "iterations": 1,
        "tokens": {"input": 10, "output": 15},
    }

    class DummyExecutor:
        def execute(self, **kwargs):
            return mock_result

    monkeypatch.setattr(server, "get_executor", lambda: DummyExecutor())
    client = TestClient(app)

    resp = client.post("/execute", json={"task": "Write a Python function"})
    assert resp.status_code == 200
    data = resp.json()

    expected_top_level = ["success", "output", "tool_calls", "iterations", "tokens"]
    for f in expected_top_level:
        assert f in data
    assert len(data) > 0, "Response should have fields"


@pytest.mark.asyncio
async def test_config_mode_default_is_native():
    """Test that default execution mode from config is 'native'."""
    cfg = get_config()
    mode = cfg.execution.mode
    assert mode == "native"


@pytest.mark.asyncio
async def test_config_reload_changes_mode():
    """Test that config can be modified and reloaded."""
    # Get current config
    cfg = get_config()
    current_mode = cfg.execution.mode
    assert current_mode == "native"

    # Modify config to api mode
    config_path = Path.home() / ".sago" / "config" / "sago.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Change mode
    config["execution"]["mode"] = "api"
    with open(config_path, "w") as f:
        yaml.dump(config, f)

    # Reload config
    invalidate_config_cache()
    cfg = get_config()
    new_mode = cfg.execution.mode
    assert new_mode == "api"

    # Reset config back to native
    config["execution"]["mode"] = "native"
    with open(config_path, "w") as f:
        yaml.dump(config, f)
    invalidate_config_cache()


@pytest.mark.asyncio
async def test_execute_endpoint_with_model(monkeypatch):
    """Test /execute with model field in request."""
    from sago.api import server

    mock_result = {
        "success": True,
        "output": "def add(a, b): return a + b",
        "tool_calls": [],
        "iterations": 1,
        "tokens": {"input": 10, "output": 15},
    }

    class DummyExecutor:
        def execute(self, **kwargs):
            return mock_result

    monkeypatch.setattr(server, "get_executor", lambda: DummyExecutor())
    client = TestClient(app)

    resp = client.post(
        "/execute",
        json={"task": "Write a simple Python function", "agent": "python-engineer"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_ws_route_exists():
    """Test that WebSocket routes are registered."""
    routes = [r.path for r in app.routes]
    ws_related = [r for r in routes if "ws" in r.lower()]
    assert len(ws_related) > 0, "API should have WebSocket routes defined"
    assert len(routes) > 0, "API should have routes defined"


@pytest.mark.asyncio
async def test_sago_config_structure():
    """Test that SagoConfig has execution field."""
    cfg = get_config()
    assert hasattr(cfg, "execution"), "SagoConfig should have execution field"
    assert hasattr(cfg.execution, "mode"), "ExecutionConfig should have mode field"
    assert cfg.execution.mode == "native"


@pytest.mark.asyncio
async def test_reload_invalidates_cache():
    """Test that invalidate_config_cache works correctly."""
    invalidate_config_cache()
    cfg = get_config()
    assert cfg is not None
    assert hasattr(cfg, "execution")


@pytest.mark.asyncio
async def test_execute_request_model():
    """Test that ExecuteRequest Pydantic model works."""
    # Test creating a valid request
    request = ExecuteRequest(task="test task", agent="python-engineer")
    assert request.task == "test task"
    assert request.agent == "python-engineer"

    # Test with just task
    request2 = ExecuteRequest(task="another task")
    assert request2.task == "another task"
    assert request2.agent is None
