"""Source discovery runs and candidate sources."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "013_source_discovery"
down_revision: Union[str, None] = "012_verification_cache_uuid"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

discovery_run_status = postgresql.ENUM(
    "running", "completed", "failed", name="discoveryrunstatus", create_type=False
)
discovery_run_stage = postgresql.ENUM(
    "searching", "evaluating", "done", name="discoveryrunstage", create_type=False
)
candidate_evaluation_verdict = postgresql.ENUM(
    "recurring_source", "one_off_page", "unclear", name="candidateevaluationverdict", create_type=False
)
candidate_source_status = postgresql.ENUM(
    "pending_review", "approved", "rejected", "needs_more_info",
    name="candidatesourcestatus", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    discovery_run_status.create(bind, checkfirst=True)
    discovery_run_stage.create(bind, checkfirst=True)
    candidate_evaluation_verdict.create(bind, checkfirst=True)
    candidate_source_status.create(bind, checkfirst=True)

    op.create_table(
        "discovery_runs",
        sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("status", discovery_run_status, nullable=False, server_default="running"),
        sa.Column("current_stage", discovery_run_stage, nullable=False, server_default="searching"),
        sa.Column("queries_used", postgresql.JSONB(astext_type=sa.Text()), server_default="[]"),
        sa.Column("candidates_found", sa.Integer(), server_default="0"),
        sa.Column("candidates_evaluated", sa.Integer(), server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("triggered_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), server_default="{}"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_discovery_runs_user_id", "discovery_runs", ["user_id"])

    op.create_table(
        "candidate_sources",
        sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("discovery_run_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("discovered_url", sa.Text(), nullable=False),
        sa.Column("evaluation_verdict", candidate_evaluation_verdict, nullable=False),
        sa.Column("relevance_notes", sa.Text(), server_default=""),
        sa.Column("legitimacy_notes", sa.Text(), server_default=""),
        sa.Column("confidence", sa.Float(), server_default="0"),
        sa.Column("guessed_parser_config", postgresql.JSONB(astext_type=sa.Text()), server_default="{}"),
        sa.Column("status", candidate_source_status, nullable=False, server_default="pending_review"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["discovery_run_id"], ["discovery_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_candidate_sources_discovery_run_id", "candidate_sources", ["discovery_run_id"])
    op.create_index("ix_candidate_sources_domain", "candidate_sources", ["domain"])


def downgrade() -> None:
    op.drop_index("ix_candidate_sources_domain", table_name="candidate_sources")
    op.drop_index("ix_candidate_sources_discovery_run_id", table_name="candidate_sources")
    op.drop_table("candidate_sources")
    op.drop_index("ix_discovery_runs_user_id", table_name="discovery_runs")
    op.drop_table("discovery_runs")

    bind = op.get_bind()
    candidate_source_status.drop(bind, checkfirst=True)
    candidate_evaluation_verdict.drop(bind, checkfirst=True)
    discovery_run_stage.drop(bind, checkfirst=True)
    discovery_run_status.drop(bind, checkfirst=True)
