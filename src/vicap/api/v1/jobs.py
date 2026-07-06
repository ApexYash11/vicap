from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from vicap.core.auth import get_api_key_id
from vicap.core.db import get_session
from vicap.models.schemas import JobCreateResponse, JobResponse
from vicap.models.sql import Job as JobModel

logger = logging.getLogger(__name__)
router = APIRouter(tags=["jobs"])


@router.get("/jobs", response_model=list[JobResponse])
async def list_jobs(
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
    api_key_id: str = Depends(get_api_key_id),
    db: AsyncSession = Depends(get_session),
) -> list[JobResponse]:
    query = select(JobModel).order_by(JobModel.queued_at.desc())
    if status:
        query = query.where(JobModel.status == status)
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    jobs = result.scalars().all()
    return [_job_to_response(j) for j in jobs]


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: UUID,
    api_key_id: str = Depends(get_api_key_id),
    db: AsyncSession = Depends(get_session),
) -> JobResponse:
    result = await db.execute(select(JobModel).where(JobModel.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job not found")
    return _job_to_response(job)


@router.post("/jobs/{job_id}/cancel", response_model=JobResponse)
async def cancel_job(
    job_id: UUID,
    api_key_id: str = Depends(get_api_key_id),
    db: AsyncSession = Depends(get_session),
) -> JobResponse:
    result = await db.execute(select(JobModel).where(JobModel.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job not found")
    if job.status not in ("queued", "running"):
        raise HTTPException(400, f"Cannot cancel job in status: {job.status}")

    job.status = "cancelled"
    await db.commit()
    await db.refresh(job)
    return _job_to_response(job)


def _job_to_response(job: JobModel) -> JobResponse:
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
