"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("key_hash", sa.String(64), unique=True, nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("rate_limit", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("mode", sa.String(20), nullable=False, server_default=sa.text("'media'")),
        sa.Column("source_path", sa.Text(), nullable=True),
        sa.Column("source_filename", sa.String(255), nullable=True),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default=sa.text("'created'"), index=True
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=True, server_default=sa.text("0")),
        sa.Column("rolling_summary", sa.Text(), nullable=True),
        sa.Column("captions_data", postgresql.JSONB(), nullable=True),
        sa.Column("scenes_data", postgresql.JSONB(), nullable=True),
        sa.Column("transcripts_data", postgresql.JSONB(), nullable=True),
        sa.Column("action_items", postgresql.JSONB(), nullable=True),
        sa.Column("qa_history", postgresql.JSONB(), nullable=True),
        sa.Column("ledger_data", postgresql.JSONB(), nullable=True),
        sa.Column(
            "api_key_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("api_keys.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    op.create_table(
        "jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("job_type", sa.String(20), nullable=False, server_default=sa.text("'batch'")),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default=sa.text("'queued'"), index=True
        ),
        sa.Column("progress", postgresql.JSONB(), nullable=True, server_default=sa.text("'{}'")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "queued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("jobs")
    op.drop_table("sessions")
    op.drop_table("api_keys")
