from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Text, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from vicap.core.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key_hash = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    rate_limit = Column(Integer, default=100, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    sessions = relationship("Session", back_populates="api_key")


class Session(Base):
    __tablename__ = "sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mode = Column(String(20), default="media", nullable=False)
    source_path = Column(Text, nullable=True)
    source_filename = Column(String(255), nullable=True)
    status = Column(
        String(20),
        default="created",
        nullable=False,
        index=True,
    )
    error_message = Column(Text, nullable=True)
    chunk_count = Column(Integer, default=0)
    rolling_summary = Column(Text, nullable=True)

    captions_data = Column(JSON, nullable=True)
    scenes_data = Column(JSON, nullable=True)
    transcripts_data = Column(JSON, nullable=True)
    action_items = Column(JSON, nullable=True)
    qa_history = Column(JSON, nullable=True)
    ledger_data = Column(JSON, nullable=True)

    api_key_id = Column(
        UUID(as_uuid=True),
        ForeignKey("api_keys.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

    api_key = relationship("ApiKey", back_populates="sessions")
    jobs = relationship("Job", back_populates="session", cascade="all, delete-orphan")


class Job(Base):
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    job_type = Column(String(20), default="batch", nullable=False)
    status = Column(
        String(20),
        default="queued",
        nullable=False,
        index=True,
    )
    progress = Column(JSON, default=dict, nullable=True)
    error_message = Column(Text, nullable=True)
    queued_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    session = relationship("Session", back_populates="jobs")
