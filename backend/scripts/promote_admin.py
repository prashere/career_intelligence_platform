#!/usr/bin/env python3
"""Promote an existing user to administrator.

Usage:
    python scripts/promote_admin.py admin@localhost
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.database import async_session
from app.models import User, UserRole
from app.services.auth import get_user_by_email


async def main(email: str) -> int:
    async with async_session() as session:
        user = await get_user_by_email(session, email)
        if not user:
            print(f"No user found: {email}")
            return 1
        user.role = UserRole.administrator
        await session.commit()
    print(f"Promoted {email} to administrator")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/promote_admin.py <email>")
        raise SystemExit(1)
    raise SystemExit(asyncio.run(main(sys.argv[1])))
