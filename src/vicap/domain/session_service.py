from __future__ import annotations

import json
import logging
from uuid import UUID, uuid4
from datetime import datetime, timezone

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from vicap.models.domain import SessionMemory
from vicap.models.sql import Session as SessionModel, ApiKey as ApiKeyModel

logger = logging.getLogger(__name__)


class SessionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_session_record(
        self,
        session_id: str | None = None,
        mode: str = "media",
        source_path: str | None = None,
        source_filename: str | None = None,
        api_key_id: str | None = None,
    ) -> SessionModel:
        session = SessionModel(
            id=UUID(session_id) if session_id else uuid4(),
            mode=mode,
            source_path=source_path,
            source_filename=source_filename,
            status="created",
            api_key_id=UUID(api_key_id) if api_key_id else None,
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def persist_session(
        self,
        session_id: str,
        memory: SessionMemory,
        ledger: dict | None = None,
    ) -> SessionModel | None:
        try:
            sid = UUID(session_id)
        except ValueError:
            return None
        result = await self.db.execute(select(SessionModel).where(SessionModel.id == sid))
        session = result.scalar_one_or_none()
        if not session:
            logger.warning("Session %s not found for persistence", session_id)
            return None

        session.status = "completed"
        session.chunk_count = memory.chunk_count
        session.rolling_summary = memory.rolling_summary
        session.captions_data = memory.captions_by_style
        session.scenes_data = [s.to_dict() for s in memory.scenes]
        session.transcripts_data = [t.to_dict() for t in memory.transcripts]
        session.action_items = [a.to_dict() for a in memory.action_items]
        session.qa_history = [q.to_dict() for q in memory.qa_history]
        session.ledger_data = ledger or {}
        session.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(session)
        logger.info("Persisted session %s to PostgreSQL", session_id)
        return session

    async def get_session_by_id(self, session_id: str) -> SessionModel | None:
        try:
            sid = UUID(session_id)
        except ValueError:
            return None
        result = await self.db.execute(select(SessionModel).where(SessionModel.id == sid))
        return result.scalar_one_or_none()

    async def list_sessions(
        self,
        api_key_id: str | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[SessionModel]:
        query = select(SessionModel).order_by(desc(SessionModel.created_at))
        if api_key_id:
            query = query.where(SessionModel.api_key_id == UUID(api_key_id))
        if status:
            query = query.where(SessionModel.status == status)
        query = query.offset(offset).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_sessions(
        self,
        api_key_id: str | None = None,
        status: str | None = None,
    ) -> int:
        query = select(func.count(SessionModel.id))
        if api_key_id:
            query = query.where(SessionModel.api_key_id == UUID(api_key_id))
        if status:
            query = query.where(SessionModel.status == status)
        result = await self.db.execute(query)
        return result.scalar() or 0

    async def delete_session_record(self, session_id: str) -> bool:
        try:
            sid = UUID(session_id)
        except ValueError:
            return False
        result = await self.db.execute(select(SessionModel).where(SessionModel.id == sid))
        session = result.scalar_one_or_none()
        if not session:
            return False
        await self.db.delete(session)
        await self.db.commit()
        return True

    async def update_status(
        self, session_id: str, status: str, error_message: str | None = None
    ) -> bool:
        try:
            sid = UUID(session_id)
        except ValueError:
            return False
        result = await self.db.execute(select(SessionModel).where(SessionModel.id == sid))
        session = result.scalar_one_or_none()
        if not session:
            return False
        session.status = status
        session.updated_at = datetime.now(timezone.utc)
        if error_message:
            session.error_message = error_message
        await self.db.commit()
        return True
