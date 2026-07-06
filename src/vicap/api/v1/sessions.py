from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from vicap.config import get_settings
from vicap.core.auth import get_api_key_id
from vicap.core.db import get_session
from vicap.models import SessionMode
from vicap.models.schemas import (
    AskRequest,
    AskResponse,
    BatchProcessResponse,
    SessionResponse,
)
from vicap.pipeline import Pipeline
from vicap.session.store import SessionStore

logger = logging.getLogger(__name__)
router = APIRouter(tags=["sessions"])

pipeline = Pipeline(store=SessionStore(get_settings().redis_url))


@router.post("/sessions/batch", response_model=BatchProcessResponse)
async def batch_process(
    file: UploadFile = File(...),
    mode: SessionMode = Query(default=SessionMode.MEDIA),
    api_key_id: str = Depends(get_api_key_id),
    db: AsyncSession = Depends(get_session),
) -> BatchProcessResponse:
    settings = get_settings()
    if not settings.has_api_key:
        raise HTTPException(503, "FIREWORKS_API_KEY not configured")

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    upload_path = settings.data_dir / "clips" / file.filename
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    upload_path.write_bytes(await file.read())

    memory = await pipeline.process_batch(upload_path, mode=mode)
    return BatchProcessResponse(
        session_id=memory.session_id,
        captions=memory.captions_by_style,
        summary=memory.rolling_summary,
        action_items=[a.to_dict() for a in memory.action_items],
        ledger=pipeline.client.ledger.to_dict(),
    )


@router.post("/sessions/stream")
async def stream_process(
    file: UploadFile = File(...),
    mode: SessionMode = Query(default=SessionMode.MEDIA),
    api_key_id: str = Depends(get_api_key_id),
):
    settings = get_settings()
    if not settings.has_api_key:
        raise HTTPException(503, "FIREWORKS_API_KEY not configured")

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    upload_path = settings.data_dir / "clips" / file.filename
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    upload_path.write_bytes(await file.read())

    async def event_generator():
        async for event in pipeline.stream_session(upload_path, mode=mode):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    api_key_id: str = Depends(get_api_key_id),
) -> SessionResponse:
    memory = await pipeline.store.get(session_id)
    if not memory:
        raise HTTPException(404, "Session not found")
    data = memory.to_dict()
    return SessionResponse(**data)


@router.post("/sessions/{session_id}/ask", response_model=AskResponse)
async def ask_session(
    session_id: str,
    body: AskRequest,
    api_key_id: str = Depends(get_api_key_id),
) -> AskResponse:
    settings = get_settings()
    if not settings.has_api_key:
        raise HTTPException(503, "FIREWORKS_API_KEY not configured")
    try:
        result = await pipeline.ask_session(session_id, body.question, body.mode)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc

    return AskResponse(
        question=result.question,
        answer=result.answer,
        citations=result.citations,
        mode=result.mode.value,
        timestamp=result.timestamp,
    )


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    api_key_id: str = Depends(get_api_key_id),
):
    await pipeline.store.delete(session_id)
