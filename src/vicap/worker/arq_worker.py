from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import arq
from sqlalchemy.ext.asyncio import AsyncSession

from vicap.config import get_settings
from vicap.core.db import get_session_maker
from vicap.domain.job_service import JobService
from vicap.domain.session_service import SessionService
from vicap.pipeline import Pipeline
from vicap.session.store import SessionStore

logger = logging.getLogger(__name__)


async def process_video_job(ctx: dict, session_id: str, job_id: str, file_path: str) -> dict:
    maker = get_session_maker()
    async with maker() as db:
        job_svc = JobService(db)
        session_svc = SessionService(db)

        job = await job_svc.get_job(job_id)
        if not job or job.status == "cancelled":
            logger.info("Job %s skipped (status: %s)", job_id, job.status if job else "not found")
            return {"status": "cancelled"}

        await job_svc.update_status(job_id, "running")
        await session_svc.update_status(session_id, "processing")

        async def on_progress(done: int, total: int) -> None:
            await job_svc.update_status(
                job_id, "running", progress={"chunks_done": done, "chunks_total": total}
            )

        pipeline = Pipeline(
            store=SessionStore(get_settings().redis_url),
            progress_callback=on_progress,
        )

        try:
            memory = await pipeline.process_batch(
                Path(file_path),
                session_id=session_id,
            )

            await session_svc.persist_session(
                session_id,
                memory,
                ledger=pipeline.client.ledger.to_dict(),
            )
            await job_svc.update_status(job_id, "completed")

            logger.info("Job %s completed for session %s", job_id, session_id)
            return {"status": "completed", "session_id": session_id}

        except Exception as exc:
            logger.exception("Job %s failed: %s", job_id, exc)
            await job_svc.update_status(job_id, "failed", error_message=str(exc))
            await session_svc.update_status(session_id, "failed", str(exc))
            return {"status": "failed", "error": str(exc)}


class WorkerSettings:
    functions = [process_video_job]
    redis_settings = arq.connection.RedisSettings.from_dsn(get_settings().redis_jobs_url)
    poll_delay = 0.5
    max_jobs = 5


def main() -> None:
    asyncio.run(arq.run.Worker(WorkerSettings).run())


if __name__ == "__main__":
    main()
