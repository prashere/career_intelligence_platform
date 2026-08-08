"""Link user_profiles to users account table."""

from typing import Sequence, Union
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "002_link_profiles_to_users"
down_revision: Union[str, None] = "001_initial_auth_schedulers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(inspector, table: str) -> set[str]:
    return {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    profile_cols = _column_names(inspector, "user_profiles")

    if "user_id" in profile_cols:
        return

    op.add_column("user_profiles", sa.Column("user_id", sa.UUID(as_uuid=False), nullable=True))

    profiles = bind.execute(sa.text("SELECT id, name FROM user_profiles")).fetchall()
    for profile_id, name in profiles:
        profile_id_str = str(profile_id)
        user_id = str(uuid4())
        email = f"legacy-{profile_id_str[:8]}@migrate.local"
        bind.execute(
            sa.text(
                """
                INSERT INTO users (id, email, password_hash, role, is_active, created_at, updated_at)
                VALUES (:id, :email, :password_hash, 'user', true, now(), now())
                """
            ),
            {
                "id": user_id,
                "email": email,
                "password_hash": "!",
            },
        )
        bind.execute(
            sa.text("UPDATE user_profiles SET user_id = :user_id WHERE id = :profile_id"),
            {"user_id": user_id, "profile_id": profile_id_str},
        )

    op.alter_column("user_profiles", "user_id", nullable=False)
    op.create_unique_constraint("uq_user_profiles_user_id", "user_profiles", ["user_id"])
    op.create_foreign_key(
        "fk_user_profiles_user_id_users",
        "user_profiles",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "user_id" not in _column_names(inspector, "user_profiles"):
        return

    op.drop_constraint("fk_user_profiles_user_id_users", "user_profiles", type_="foreignkey")
    op.drop_constraint("uq_user_profiles_user_id", "user_profiles", type_="unique")
    op.drop_column("user_profiles", "user_id")
