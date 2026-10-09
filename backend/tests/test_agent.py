"""Agent evaluation regression tests."""

from app.agents.career_agent import find_connections


async def test_find_connections():
    profile = {"projects": ["Harbor Survey"], "connections": ["Dr. Hale"]}
    context = "Harbor Survey project and Dr. Hale lab work on applied ML"
    results = await find_connections(profile, context)
    assert len(results) >= 1
