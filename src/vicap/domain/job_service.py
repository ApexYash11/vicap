from __future__ import annotations

import logging
from uuid import UUID, uuid4
from datetime import datetime, timezone

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from vicap.models.sql import Job as JobModel

logger = logging.getLogger(__name__)


class JobService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_job(
        self,
        session_id: str,
        job_type: str = "batch",
    ) -> JobModel:
        job = JobModel(
            id=uuid4(),
            session_id=UUID(session_id),
            job_type=job_type,
            status="queued",
        )
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def get_job(self, job_id: str) -> JobModel | None:
        result = await self.db.execute(select(JobModel).where(JobModel.id == UUID(job_id)))
        return result.scalar_one_or_none()

    async def list_jobs(
        self,
        session_id: str | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[JobModel]:
        query = select(JobModel).order_by(desc(JobModel.queued_at))
        if session_id:
            query = query.where(JobModel.session_id == UUID(session_id))
        if status:
            query = query.where(JobModel.status == status)
        query = query.offset(offset).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_status(
        self,
        job_id: str,
        status: str,
        error_message: str | None = None,
        progress: dict | None = None,
    ) -> JobModel | None:
        result = await self.db.execute(select(JobModel).where(JobModel.id == UUID(job_id)))
        job = result.scalar_one_or_none()
        if not job:
            return None
        job.status = status
        if status == "running":
            job.started_at = datetime.now(timezone.utc)
        if status in ("completed", "failed", "cancelled"):
            job.completed_at = datetime.now(timezone.utc)
        if error_message:
            job.error_message = error_message
        if progress is not None:
            job.progress = progress
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def cancel_job(self, job_id: str) -> JobModel | None:
        job = await self.get_job(job_id)
        if not job:
            return None
        if job.status not in ("queued", "running"):
            raise ValueError(f"Cannot cancel job in status: {job.status}")
        job.status = "cancelled"
        job.completed_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(job)
        return job
