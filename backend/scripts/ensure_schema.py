"""Create any ORM tables not yet covered by Alembic migrations."""

from __future__ import annotations

import asyncio

from app.database import Base, engine
import app.models  # noqa: F401 — register all model metadata on Base


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Schema ensured (create_all)")


if __name__ == "__main__":
    asyncio.run(main())
