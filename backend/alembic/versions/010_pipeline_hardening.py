"""Feedback affinity, status history."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010_pipeline_hardening"
down_revision: Union[str, None] = "009_verification_layer"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "user_opportunities" not in inspector.get_table_names():
        return
    op.execute(
        "ALTER TABLE user_opportunities ADD COLUMN IF NOT EXISTS status_history JSONB "
        "DEFAULT '[]'::jsonb NOT NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE user_opportunities DROP COLUMN IF EXISTS status_history")
