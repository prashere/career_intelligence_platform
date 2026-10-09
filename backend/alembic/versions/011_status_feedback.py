"""Status feedback: applied/dismissed enum values, dismiss_reason, status_changed_at."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011_status_feedback"
down_revision: Union[str, None] = "010_pipeline_hardening"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "user_opportunities" not in inspector.get_table_names():
        # Table + enum are created later by Base.metadata.create_all on API boot.
        return

    # ALTER TYPE ... ADD VALUE cannot run in the same transaction that uses the new value.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE useropportunitystatus ADD VALUE IF NOT EXISTS 'applied'")
        op.execute("ALTER TYPE useropportunitystatus ADD VALUE IF NOT EXISTS 'dismissed'")

    cols = {c["name"] for c in inspector.get_columns("user_opportunities")}
    if "dismiss_reason" not in cols:
        op.add_column(
            "user_opportunities",
            sa.Column("dismiss_reason", sa.String(length=32), nullable=True),
        )
    if "status_changed_at" not in cols:
        op.add_column(
            "user_opportunities",
            sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True),
        )
    op.execute(
        "UPDATE user_opportunities SET status_changed_at = updated_at "
        "WHERE status_changed_at IS NULL"
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "user_opportunities" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("user_opportunities")}
    if "status_changed_at" in cols:
        op.drop_column("user_opportunities", "status_changed_at")
    if "dismiss_reason" in cols:
        op.drop_column("user_opportunities", "dismiss_reason")
