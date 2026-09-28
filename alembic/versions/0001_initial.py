"""Initial migration: traces and spans tables.

Revision ID: 0001
Revises:
Create Date: 2026-09-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create traces and spans tables with PostgreSQL JSONB fields."""
    op.create_table(
        "traces",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column(
            "resource_attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("schema_url", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trace_id"),
    )
    op.create_index(op.f("ix_traces_trace_id"), "traces", ["trace_id"], unique=True)

    op.create_table(
        "spans",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trace_id", sa.Integer(), nullable=False),
        sa.Column("span_id", sa.String(length=32), nullable=False),
        sa.Column("parent_span_id", sa.String(length=32), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.Integer(), nullable=True),
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "events",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "links",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("status_description", sa.Text(), nullable=True),
        sa.Column("start_time_unix_nano", sa.BigInteger(), nullable=False),
        sa.Column("end_time_unix_nano", sa.BigInteger(), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("scope_name", sa.String(length=255), nullable=True),
        sa.Column("scope_version", sa.String(length=64), nullable=True),
        sa.Column(
            "scope_attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["trace_id"], ["traces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_spans_trace_id"), "spans", ["trace_id"], unique=False)
    op.create_index(op.f("ix_spans_span_id"), "spans", ["span_id"], unique=False)


def downgrade() -> None:
    """Drop spans and traces tables."""
    op.drop_index(op.f("ix_spans_span_id"), table_name="spans")
    op.drop_index(op.f("ix_spans_trace_id"), table_name="spans")
    op.drop_table("spans")
    op.drop_index(op.f("ix_traces_trace_id"), table_name="traces")
    op.drop_table("traces")
