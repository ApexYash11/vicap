from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)
    mode: str = Field(default="qa", pattern="^(qa|plan|model|debug)$")


class HealthResponse(BaseModel):
    status: str
    has_api_key: bool
    kimi_model: str
    minimax_model: str
    db_connected: bool = False


class BatchProcessResponse(BaseModel):
    session_id: str
    captions: dict[str, list[str]]
    summary: str
    action_items: list[dict[str, Any]]
    ledger: dict[str, int]


class StreamSessionResponse(BaseModel):
    session_id: str
    status: str


class SessionResponse(BaseModel):
    session_id: str
    mode: str
    source_path: str | None
    created_at: str
    status: str
    captions_by_style: dict[str, list[str]] = {}
    scenes: list[dict[str, Any]] = []
    transcripts: list[dict[str, Any]] = []
    rolling_summary: str = ""
    action_items: list[dict[str, Any]] = []
    qa_history: list[dict[str, Any]] = []
    ledger: dict[str, int] | None = None


class JobCreateResponse(BaseModel):
    job_id: str
    session_id: str
    status: str = "queued"
    poll_url: str


class JobResponse(BaseModel):
    job_id: str
    session_id: str
    job_type: str
    status: str
    progress: dict[str, Any] = {}
    error_message: str | None = None
    queued_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ClipListResponse(BaseModel):
    clips: list[str]


class AskResponse(BaseModel):
    question: str
    answer: str
    citations: list[str] = []
    mode: str
    timestamp: str


class ErrorResponse(BaseModel):
    error: bool = True
    error_code: str
    detail: str
