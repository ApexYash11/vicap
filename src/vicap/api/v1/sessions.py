from __future__ import annotations

import json
import logging
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

import arq

from vicap.config import get_settings
from vicap.core.auth import get_api_key_id
from vicap.core.db import get_session
from vicap.domain.job_service import JobService
from vicap.domain.session_service import SessionService
from vicap.models import SessionMode
from vicap.models.schemas import (
    AskRequest,
    AskResponse,
    BatchProcessResponse,
    JobCreateResponse,
    SessionResponse,
)
from vicap.models.sql import Session as SessionModel
from vicap.pipeline import Pipeline
from vicap.session.store import SessionStore

logger = logging.getLogger(__name__)
router = APIRouter(tags=["sessions"])

pipeline = Pipeline(store=SessionStore(get_settings().redis_url))


async def _enqueue_arq_job(session_id: str, job_id: str, file_path: str) -> None:
    redis = await arq.create_pool(
        arq.connection.RedisSettings.from_dsn(get_settings().redis_jobs_url)
    )
    try:
        await redis.enqueue_job("process_video_job", session_id, job_id, file_path)
    finally:
        redis.close()


def _session_to_response(s: SessionModel) -> SessionResponse:
    return SessionResponse(
        session_id=str(s.id),
        mode=s.mode,
        source_path=s.source_path,
        created_at=s.created_at.isoformat() if s.created_at else "",
        status=s.status,
        captions_by_style=s.captions_data or {},
        scenes=s.scenes_data or [],
        transcripts=s.transcripts_data or [],
        rolling_summary=s.rolling_summary or "",
        action_items=s.action_items or [],
        qa_history=s.qa_history or [],
        ledger=s.ledger_data,
    )


@router.post("/sessions", status_code=202, response_model=JobCreateResponse)
async def create_session(
    file: UploadFile = File(...),
    mode: SessionMode = Query(default=SessionMode.MEDIA),
    api_key_id: str = Depends(get_api_key_id),
    db: AsyncSession = Depends(get_session),
) -> JobCreateResponse:
    settings = get_settings()
    if not settings.has_api_key:
        raise HTTPException(503, "FIREWORKS_API_KEY not configured")

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    upload_dir = settings.data_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    upload_path = upload_dir / file.filename
    upload_path.write_bytes(await file.read())

    session_svc = SessionService(db)
    job_svc = JobService(db)

    session = await session_svc.create_session_record(
        mode=mode.value,
        source_path=str(upload_path),
        source_filename=file.filename,
        api_key_id=api_key_id,
    )

    session_id = str(session.id)
    memory = await pipeline.store.get(session_id)
    if not memory:
        from vicap.models import SessionMemory

        mem = SessionMemory(session_id=session_id, mode=mode, source_path=str(upload_path))
        mem.status = "created"
        await pipeline.store.save(mem)

    job = await job_svc.create_job(session_id, job_type="batch")
    await _enqueue_arq_job(session_id, str(job.id), str(upload_path))

    return JobCreateResponse(
        job_id=str(job.id),
        session_id=session_id,
        status="queued",
        poll_url=f"/api/v1/jobs/{job.id}",
    )


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

    session_svc = SessionService(db)
    await session_svc.persist_session(
        memory.session_id, memory, ledger=pipeline.client.ledger.to_dict()
    )

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


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
    api_key_id: str = Depends(get_api_key_id),
    db: AsyncSession = Depends(get_session),
) -> list[SessionResponse]:
    session_svc = SessionService(db)
    sessions = await session_svc.list_sessions(
        api_key_id=api_key_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return [_session_to_response(s) for s in sessions]


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    api_key_id: str = Depends(get_api_key_id),
    db: AsyncSession = Depends(get_session),
) -> SessionResponse:
    session_svc = SessionService(db)
    record = await session_svc.get_session_by_id(session_id)
    if not record:
        memory = await pipeline.store.get(session_id)
        if not memory:
            raise HTTPException(404, "Session not found")
        data = memory.to_dict()
        return SessionResponse(**data)
    return _session_to_response(record)


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


@router.post("/sessions/{session_id}/reprocess", status_code=202, response_model=JobCreateResponse)
async def reprocess_session(
    session_id: str,
    api_key_id: str = Depends(get_api_key_id),
    db: AsyncSession = Depends(get_session),
) -> JobCreateResponse:
    session_svc = SessionService(db)
    job_svc = JobService(db)

    record = await session_svc.get_session_by_id(session_id)
    if not record:
        memory = await pipeline.store.get(session_id)
        if not memory:
            raise HTTPException(404, "Session not found")
        source_path = memory.source_path
    else:
        source_path = record.source_path or ""

    if not source_path or not Path(source_path).exists():
        raise HTTPException(400, "Session has no valid source file for reprocessing")

    await session_svc.update_status(session_id, "created")
    job = await job_svc.create_job(session_id, job_type="batch")
    await _enqueue_arq_job(session_id, str(job.id), source_path)

    return JobCreateResponse(
        job_id=str(job.id),
        session_id=session_id,
        status="queued",
        poll_url=f"/api/v1/jobs/{job.id}",
    )


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    api_key_id: str = Depends(get_api_key_id),
    db: AsyncSession = Depends(get_session),
):
    session_svc = SessionService(db)
    await session_svc.delete_session_record(session_id)
    await pipeline.store.delete(session_id)
