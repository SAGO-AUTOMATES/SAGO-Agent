from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HealthCheck(BaseModel):
    status: str = "ok"
    version: str = "0.1.13"


class ConfigUpdate(BaseModel):
    key: str
    value: str
    section: str = "general"


class TaskRequest(BaseModel):
    task: str = Field(..., description="The task to execute")
    agent: str | None = Field(default=None, description="Specific agent to use")
    model: str | None = Field(default=None, description="LLM model override")
    effort: str | None = Field(default=None, description="Effort level: low/medium/high/max")
    max_tokens: int | None = Field(default=None, ge=1, le=50000)
    max_iterations: int | None = Field(default=None, ge=1, le=50)


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    progress: float = 0.0
    current_agent: str | None = None
    output: str | None = None
    iteration: int = 0


class ExecuteResponse(BaseModel):
    task_id: str
    status: str = "started"
    message: str = "Task execution started"
    result: dict[str, Any] | None = None


class SessionInfo(BaseModel):
    id: str
    title: str
    created_at: str
    status: str
    message_count: int = 0
    tool_count: int = 0


class ApiKeyConfig(BaseModel):
    name: str
    env_key: str
    current_value: str = ""
    masked: str = ""


class ProviderConfig(BaseModel):
    name: str
    enabled: bool
    default_model: str
    api_key_env: str | None = None
