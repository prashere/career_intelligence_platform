"""Ingestion hardening: score breakdown, source outcome stats, opportunity ingestion meta."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008_ingestion_hardening"
down_revision: Union[str, None] = "007_profile_db_storage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    # Legacy app tables (user_opportunities etc.) are created via Base.metadata.create_all.
    if "user_opportunities" in tables:
        op.execute(
            "ALTER TABLE user_opportunities ADD COLUMN IF NOT EXISTS score_breakdown JSONB"
        )
    if "opportunity_sources" in tables:
        op.execute(
            "ALTER TABLE opportunity_sources ADD COLUMN IF NOT EXISTS outcome_stats JSONB"
        )
    if "opportunities" in tables:
        op.execute(
            "ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS ingestion_meta JSONB"
        )


def downgrade() -> None:
    op.execute("ALTER TABLE opportunities DROP COLUMN IF EXISTS ingestion_meta")
    op.execute("ALTER TABLE opportunity_sources DROP COLUMN IF EXISTS outcome_stats")
    op.execute("ALTER TABLE user_opportunities DROP COLUMN IF EXISTS score_breakdown")
