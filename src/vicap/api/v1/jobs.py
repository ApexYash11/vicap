from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from vicap.core.auth import get_api_key_id
from vicap.core.db import get_session
from vicap.domain.job_service import JobService
from vicap.models.schemas import JobResponse, JobCreateResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["jobs"])


def _job_to_response(job) -> JobResponse:
    return JobResponse(
        job_id=str(job.id),
        session_id=str(job.session_id),
        job_type=job.job_type,
        status=job.status,
        progress=job.progress or {},
        error_message=job.error_message,
        queued_at=job.queued_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


@router.get("/jobs", response_model=list[JobResponse])
async def list_jobs(
    session_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    api_key_id: str = Depends(get_api_key_id),
    db: AsyncSession = Depends(get_session),
) -> list[JobResponse]:
    job_svc = JobService(db)
    jobs = await job_svc.list_jobs(
        session_id=session_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return [_job_to_response(j) for j in jobs]


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: UUID,
    api_key_id: str = Depends(get_api_key_id),
    db: AsyncSession = Depends(get_session),
) -> JobResponse:
    job_svc = JobService(db)
    job = await job_svc.get_job(str(job_id))
    if not job:
        raise HTTPException(404, "Job not found")
    return _job_to_response(job)


@router.post("/jobs/{job_id}/cancel", response_model=JobResponse)
async def cancel_job(
    job_id: UUID,
    api_key_id: str = Depends(get_api_key_id),
    db: AsyncSession = Depends(get_session),
) -> JobResponse:
    job_svc = JobService(db)
    try:
        job = await job_svc.cancel_job(str(job_id))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not job:
        raise HTTPException(404, "Job not found")
    return _job_to_response(job)
