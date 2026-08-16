"""Relevance gate: rejected_items.meta and the relevance rejection stage."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005_relevance_gate"
down_revision: Union[str, None] = "004_ingestion_trace_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(inspector, table: str, column: str) -> bool:
    if table not in inspector.get_table_names():
        return False
    return column in {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_column(inspector, "rejected_items", "meta"):
        op.add_column(
            "rejected_items",
            sa.Column(
                "meta",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
        )

    # Postgres refuses to use a new enum label inside the transaction that adds
    # it, so this runs outside the migration transaction.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE rejectedstage ADD VALUE IF NOT EXISTS 'relevance'")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_column(inspector, "rejected_items", "meta"):
        op.drop_column("rejected_items", "meta")

    # Enum labels cannot be removed in Postgres without recreating the type;
    # leaving 'relevance' in place is harmless.
