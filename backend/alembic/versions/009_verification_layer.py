"""Verification / trust layer: opportunity status, org domain cache, domain legitimacy."""

from typing import Sequence, Union

from alembic import op

revision: str = "009_verification_layer"
down_revision: Union[str, None] = "008_ingestion_hardening"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS verification_status VARCHAR(32) "
        "NOT NULL DEFAULT 'unverified'"
    )
    op.execute(
        "ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ"
    )
    op.execute(
        "ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS verification_meta JSONB"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS org_domain_cache (
            id VARCHAR NOT NULL PRIMARY KEY,
            org_key VARCHAR(255) NOT NULL UNIQUE,
            org_display_name VARCHAR(255),
            canonical_domain VARCHAR(255) NOT NULL,
            canonical_url TEXT,
            confidence DOUBLE PRECISION NOT NULL DEFAULT 0.5,
            verified_at TIMESTAMPTZ,
            meta JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_org_domain_cache_org_key ON org_domain_cache (org_key)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS domain_legitimacy_cache (
            id VARCHAR NOT NULL PRIMARY KEY,
            domain VARCHAR(255) NOT NULL UNIQUE,
            registered_at TIMESTAMPTZ,
            trust_score DOUBLE PRECISION NOT NULL DEFAULT 0.5,
            flags JSONB NOT NULL DEFAULT '[]'::jsonb,
            last_checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            meta JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_domain_legitimacy_cache_domain ON domain_legitimacy_cache (domain)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS domain_legitimacy_cache")
    op.execute("DROP TABLE IF EXISTS org_domain_cache")
    op.execute("ALTER TABLE opportunities DROP COLUMN IF EXISTS verification_meta")
    op.execute("ALTER TABLE opportunities DROP COLUMN IF EXISTS verified_at")
    op.execute("ALTER TABLE opportunities DROP COLUMN IF EXISTS verification_status")
