"""Align verification cache id columns with the UUID type used by their models.

Migration 009 created org_domain_cache.id and domain_legitimacy_cache.id as
VARCHAR while the models declare UUID. Inserts happened to work, but updates
failed with 'operator does not exist: character varying = uuid'.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "012_verification_cache_uuid"
down_revision: Union[str, None] = "011_status_feedback"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE org_domain_cache "
        "ALTER COLUMN id TYPE UUID USING id::uuid"
    )
    op.execute(
        "ALTER TABLE domain_legitimacy_cache "
        "ALTER COLUMN id TYPE UUID USING id::uuid"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE org_domain_cache "
        "ALTER COLUMN id TYPE VARCHAR USING id::text"
    )
    op.execute(
        "ALTER TABLE domain_legitimacy_cache "
        "ALTER COLUMN id TYPE VARCHAR USING id::text"
    )
