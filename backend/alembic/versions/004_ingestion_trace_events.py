"""Add ingestion_trace_events for pipeline observability."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004_ingestion_trace_events"
down_revision: Union[str, None] = "003_ingestion_pipeline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

trace_level = postgresql.ENUM("debug", "info", "warn", "error", name="tracelevel", create_type=False)


def _has_table(inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    trace_level.create(bind, checkfirst=True)

    if _has_table(inspector, "ingestion_trace_events"):
        return

    op.create_table(
        "ingestion_trace_events",
        sa.Column("id", sa.UUID(as_uuid=False), primary_key=True),
        sa.Column("run_id", sa.UUID(as_uuid=False), sa.ForeignKey("ingestion_runs.id"), nullable=False),
        sa.Column("source_id", sa.UUID(as_uuid=False), sa.ForeignKey("opportunity_sources.id"), nullable=True),
        sa.Column("seq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("level", trace_level, nullable=False, server_default="info"),
        sa.Column("event", sa.String(64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_ingestion_trace_events_run_id", "ingestion_trace_events", ["run_id"])
    op.create_index("ix_ingestion_trace_events_source_id", "ingestion_trace_events", ["source_id"])
    op.create_index("ix_ingestion_trace_events_run_seq", "ingestion_trace_events", ["run_id", "seq"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _has_table(inspector, "ingestion_trace_events"):
        op.drop_index("ix_ingestion_trace_events_run_seq", table_name="ingestion_trace_events")
        op.drop_index("ix_ingestion_trace_events_source_id", table_name="ingestion_trace_events")
        op.drop_index("ix_ingestion_trace_events_run_id", table_name="ingestion_trace_events")
        op.drop_table("ingestion_trace_events")
    trace_level.drop(bind, checkfirst=True)
