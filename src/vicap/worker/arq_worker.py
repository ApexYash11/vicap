from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import arq
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vicap.config import get_settings
from vicap.core.db import get_session_maker
from vicap.models.sql import Job as JobModel, Session as SessionModel
from vicap.pipeline import Pipeline

logger = logging.getLogger(__name__)
pipeline = Pipeline()


async def process_video_job(ctx: dict, session_id: str, job_id: str, file_path: str) -> dict:
    maker = get_session_maker()
    async with maker() as db:
        job = await _get_job(db, job_id)
        if not job or job.status == "cancelled":
            return {"status": "cancelled"}

        await _update_job_status(db, job, "running")
        await _update_session_status(db, session_id, "processing")

        try:
            memory = await pipeline.process_batch(
                Path(file_path),
                session_id=session_id,
            )

            await _update_job_progress(
                db, job, {"chunks_done": memory.chunk_count, "chunks_total": memory.chunk_count}
            )
            await _update_job_status(db, job, "completed")
            await _update_session_status(db, session_id, "completed")

            logger.info("Job %s completed for session %s", job_id, session_id)
            return {"status": "completed", "session_id": session_id}

        except Exception as exc:
            logger.exception("Job %s failed: %s", job_id, exc)
            await _update_job_status(db, job, "failed", str(exc))
            await _update_session_status(db, session_id, "failed", str(exc))
            return {"status": "failed", "error": str(exc)}


async def _get_job(db: AsyncSession, job_id: str) -> JobModel | None:
    from uuid import UUID

    result = await db.execute(select(JobModel).where(JobModel.id == UUID(job_id)))
    return result.scalar_one_or_none()


async def _update_job_status(
    db: AsyncSession, job: JobModel, status: str, error: str | None = None
) -> None:
    from datetime import datetime, timezone

    job.status = status
    if status == "running":
        job.started_at = datetime.now(timezone.utc)
    if status in ("completed", "failed", "cancelled"):
        job.completed_at = datetime.now(timezone.utc)
    if error:
        job.error_message = error
    await db.commit()


async def _update_job_progress(db: AsyncSession, job: JobModel, progress: dict) -> None:
    job.progress = progress
    await db.commit()


async def _update_session_status(
    db: AsyncSession, session_id: str, status: str, error: str | None = None
) -> None:
    from uuid import UUID

    result = await db.execute(select(SessionModel).where(SessionModel.id == UUID(session_id)))
    session = result.scalar_one_or_none()
    if session:
        session.status = status
        if error:
            session.error_message = error
        await db.commit()


class WorkerSettings:
    functions = [process_video_job]
    redis_settings = arq.connection.RedisSettings.from_dsn(get_settings().redis_jobs_url)
    poll_delay = 0.5
    max_jobs = 5


def main() -> None:
    asyncio.run(arq.run.Worker(WorkerSettings).run())


if __name__ == "__main__":
    main()
