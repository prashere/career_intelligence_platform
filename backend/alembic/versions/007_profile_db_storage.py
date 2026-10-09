"""Per-user profile storage tables (drafts, submissions, structured profile, artifacts)."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "007_profile_db_storage"
down_revision: Union[str, None] = "006_profile_pipeline_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    if "profile_intake_drafts" not in existing:
        op.create_table(
            "profile_intake_drafts",
            sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
            sa.Column("user_id", sa.UUID(as_uuid=False), nullable=False),
            sa.Column("step", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("form", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("cv_text", sa.Text(), nullable=False, server_default=""),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id"),
        )
        op.create_index("ix_profile_intake_drafts_user_id", "profile_intake_drafts", ["user_id"])

    if "profile_submissions" not in existing:
        op.create_table(
            "profile_submissions",
            sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
            sa.Column("user_id", sa.UUID(as_uuid=False), nullable=False),
            sa.Column("submission_id", sa.String(length=64), nullable=False),
            sa.Column("form", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("cv_text", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_profile_submissions_user_id", "profile_submissions", ["user_id"])
        op.create_index("ix_profile_submissions_submission_id", "profile_submissions", ["submission_id"])

    if "user_structured_profiles" not in existing:
        op.create_table(
            "user_structured_profiles",
            sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
            sa.Column("user_id", sa.UUID(as_uuid=False), nullable=False),
            sa.Column("data", postgresql.JSONB(), nullable=True),
            sa.Column("prefill", postgresql.JSONB(), nullable=True),
            sa.Column("extraction", postgresql.JSONB(), nullable=True),
            sa.Column("schema_version", sa.String(length=16), nullable=False, server_default="1.0"),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id"),
        )
        op.create_index("ix_user_structured_profiles_user_id", "user_structured_profiles", ["user_id"])

    if "user_profile_artifacts" not in existing:
        op.create_table(
            "user_profile_artifacts",
            sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
            sa.Column("user_id", sa.UUID(as_uuid=False), nullable=False),
            sa.Column("filter_config", postgresql.JSONB(), nullable=True),
            sa.Column("eligibility_rules", postgresql.JSONB(), nullable=True),
            sa.Column("ranking_config", postgresql.JSONB(), nullable=True),
            sa.Column("ingestion_sources", postgresql.JSONB(), nullable=True),
            sa.Column("profile_truth", sa.Text(), nullable=True),
            sa.Column("compiled_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id"),
        )
        op.create_index("ix_user_profile_artifacts_user_id", "user_profile_artifacts", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_profile_artifacts_user_id", table_name="user_profile_artifacts")
    op.drop_table("user_profile_artifacts")
    op.drop_index("ix_user_structured_profiles_user_id", table_name="user_structured_profiles")
    op.drop_table("user_structured_profiles")
    op.drop_index("ix_profile_submissions_submission_id", table_name="profile_submissions")
    op.drop_index("ix_profile_submissions_user_id", table_name="profile_submissions")
    op.drop_table("profile_submissions")
    op.drop_index("ix_profile_intake_drafts_user_id", table_name="profile_intake_drafts")
    op.drop_table("profile_intake_drafts")
