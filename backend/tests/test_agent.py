"""Agent evaluation regression tests."""

from app.agents.career_agent import find_connections


async def test_find_connections():
    profile = {"projects": ["TellO"], "connections": ["Calandra"]}
    context = "TellO project and Calandra lab work on applied ML"
    results = await find_connections(profile, context)
    assert len(results) >= 1
