"""Tests for profile orchestrator with mocked LLM extraction."""

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

from app.database import async_session, engine, Base
from app.models import ProfilePipelineRun, ProfilePipelineRunStatus, User, UserProfile
from app.services.profile_orchestrator import (
    create_profile_pipeline_run,
    init_pipeline_steps,
    run_profile_pipeline,
)
from app.services.profile_storage import load_structured_profile, save_submission
from tests.test_profile_pipeline import SAMPLE_EXTRACTION, SAMPLE_FORM


async def _setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _run_pipeline_test():
    await _setup_db()
    async with async_session() as session:
        user = User(email=f"pipeline-{uuid.uuid4().hex}@test.com", password_hash="x", is_active=True)
        session.add(user)
        await session.commit()
        await session.refresh(user)

        profile = UserProfile(user_id=user.id, name="Test")
        session.add(profile)
        await session.commit()

        form = dict(SAMPLE_FORM)
        cv = "Experienced ML engineer with robotics background."
        sub_id = await save_submission(session, user.id, form, cv)

        run = await create_profile_pipeline_run(session, user.id, sub_id)
        user_id, run_id, sub_id = user.id, run.id, sub_id

    async def fake_extract(prefill, cv_text, **kwargs):
        return SAMPLE_EXTRACTION

    with patch(
        "app.services.profile_orchestrator.extract_cv_from_prefill",
        new=AsyncMock(side_effect=fake_extract),
    ):
        async with async_session() as session:
            run = await run_profile_pipeline(session, run_id, user_id, sub_id)

    # The orchestrator hands off to ingest, which calls finalize_pipeline_run.
    assert run.status == ProfilePipelineRunStatus.running

    async with async_session() as session:
        structured = await load_structured_profile(session, user_id)
        assert structured is not None

        refreshed = await session.get(ProfilePipelineRun, run_id)
        assert refreshed is not None
        step_names = {s["name"]: s["status"] for s in refreshed.steps}
        assert step_names["prefill"] == "completed"
        assert step_names["extract_cv"] == "completed"
        assert step_names["merge"] == "completed"
        assert step_names["repair"] == "skipped"
        assert step_names["compile"] == "completed"
        assert step_names["activate"] == "completed"
        assert step_names["ingest"] == "pending"


def test_run_profile_pipeline_with_mocked_llm():
    asyncio.run(_run_pipeline_test())


def test_init_pipeline_steps_shape():
    steps = init_pipeline_steps()
    assert len(steps) == 7
    assert steps[0]["name"] == "prefill"
    assert steps[0]["status"] == "pending"
