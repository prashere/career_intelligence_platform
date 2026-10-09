"""Profile pipeline run tracking."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006_profile_pipeline_runs"
down_revision: Union[str, None] = "005_relevance_gate"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

profile_pipeline_run_status = postgresql.ENUM(
    "queued",
    "running",
    "completed",
    "failed",
    name="profilepipelinerunstatus",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    profile_pipeline_run_status.create(bind, checkfirst=True)

    inspector = sa.inspect(bind)
    if "profile_pipeline_runs" in inspector.get_table_names():
        return

    op.create_table(
        "profile_pipeline_runs",
        sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("submission_id", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            profile_pipeline_run_status,
            nullable=False,
            server_default="queued",
        ),
        sa.Column("current_step", sa.String(length=64), nullable=True),
        sa.Column(
            "steps",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_profile_pipeline_runs_user_id", "profile_pipeline_runs", ["user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "profile_pipeline_runs" in inspector.get_table_names():
        op.drop_index("ix_profile_pipeline_runs_user_id", table_name="profile_pipeline_runs")
        op.drop_table("profile_pipeline_runs")
    profile_pipeline_run_status.drop(bind, checkfirst=True)
