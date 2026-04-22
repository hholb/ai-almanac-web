from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

class ChatScope(BaseModel):
    kind: Literal["benchmark_run_group", "job_set"] = "benchmark_run_group"
    key: str
    title: str | None = None
    job_ids: list[str] = Field(default_factory=list)


class ChatArtifact(BaseModel):
    id: str
    kind: Literal["figure"] = "figure"
    url: str
    label: str | None = None
    filename: str | None = None
    media_type: str | None = None
    created_at: datetime


class ChatToolCall(BaseModel):
    id: str
    name: str
    status: Literal["running", "completed", "failed"] = "completed"
    input: dict = Field(default_factory=dict)
    result: Any = None
    artifacts: list[ChatArtifact] = Field(default_factory=list)


class ChatTurn(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str = ""
    created_at: datetime
    tool_calls: list[ChatToolCall] = Field(default_factory=list)
    artifacts: list[ChatArtifact] = Field(default_factory=list)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_turn_id() -> str:
    return str(uuid4())
