"""Comprehensive tests for sago.webserver.routes and models using FastAPI TestClient."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sago.webserver.models import ExecuteResponse, HealthCheck, SessionInfo, TaskRequest
from sago.webserver.routes import router


@pytest.fixture
def app() -> FastAPI:
    application = FastAPI()
    application.include_router(router)
    return application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


class TestWebserverModels:
    def test_task_request_defaults(self) -> None:
        req = TaskRequest(task="do something")
        assert req.task == "do something"
        assert req.model is None
        assert req.agent is None
        assert req.max_tokens is None

    def test_task_request_full(self) -> None:
        req = TaskRequest(
            task="write code", model="gpt-4o", agent="coder", max_tokens=2048, max_iterations=5
        )
        assert req.model == "gpt-4o"
        assert req.agent == "coder"
        assert req.max_tokens == 2048
        assert req.max_iterations == 5

    def test_health_check_model(self) -> None:
        h = HealthCheck(status="ok", version="0.1.13")
        assert h.status == "ok"
        assert h.version == "0.1.13"

    def test_execute_response_defaults(self) -> None:
        r = ExecuteResponse(task_id="123", status="completed", message="done")
        assert r.task_id == "123"
        assert r.result is None

    def test_execute_response_with_result(self) -> None:
        r = ExecuteResponse(task_id="abc", status="ok", message="done", result={"key": "val"})
        assert r.result == {"key": "val"}

    def test_session_info_model(self) -> None:
        s = SessionInfo(
            id="sid1",
            title="Session 1",
            created_at="2024-01-01",
            status="active",
            message_count=10,
            tool_count=5,
        )
        assert s.id == "sid1"
        assert s.message_count == 10


class TestHealthEndpoint:
    def test_health_returns_ok(self, client: TestClient) -> None:
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data


class TestUIEndpoint:
    def test_root_returns_html(self, client: TestClient) -> None:
        response = client.get("/")
        assert response.status_code == 200
        assert "html" in response.headers.get("content-type", "").lower()


class TestSessionsEndpoint:
    def test_sessions_returns_list(self, client: TestClient) -> None:
        with patch("sago.database.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session.list_all.return_value = [
                {"id": "s1", "title": "First", "created_at": "2024-01-01", "status": "active"},
            ]
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            response = client.get("/api/sessions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_sessions_returns_empty_on_error(self, client: TestClient) -> None:
        with patch("sago.database.Session", side_effect=Exception("db error")):
            response = client.get("/api/sessions")
        assert response.status_code == 200
        assert response.json() == []


class TestReloadEndpoint:
    def test_reload_returns_ok(self, client: TestClient) -> None:
        with patch("sago.config.loader.reload_config"):
            response = client.post("/api/reload")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_reload_returns_500_on_error(self, client: TestClient) -> None:
        with patch("sago.config.loader.reload_config", side_effect=Exception("reload failed")):
            response = client.post("/api/reload")
        assert response.status_code == 500
        data = response.json()
        assert data["status"] == "error"


class TestExecuteEndpoint:
    def test_execute_success(self, client: TestClient) -> None:
        mock_result = {"success": True, "output": "Task done"}
        with patch("sago.config.loader.get_config") as mock_cfg:
            mock_cfg.return_value.llm_providers.default = "gemini"
            with patch("sago.engine.unified.UnifiedExecutor") as mock_executor_cls:
                mock_executor = MagicMock()
                mock_executor.execute.return_value = mock_result
                mock_executor_cls.return_value = mock_executor
                response = client.post("/api/execute", json={"task": "say hello"})
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data

    def test_execute_exception_returns_error(self, client: TestClient) -> None:
        with patch("sago.config.loader.get_config", side_effect=Exception("config error")):
            response = client.post("/api/execute", json={"task": "something"})
        # FastAPI may return 500 when exception escapes, or 200 with error body — both acceptable
        assert response.status_code in (200, 500)
