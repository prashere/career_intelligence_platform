"""Status feedback API tests."""

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_patch_status_saved_queues_debounced_rerank():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Use existing seeded profile if available; skip heavy setup when unauthenticated.
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@localhost", "password": "admin"},
        )
        if login.status_code != 200:
            pytest.skip("No seeded admin user for API status test")

        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        opps = await client.get("/api/v1/opportunities?limit=1", headers=headers)
        if opps.status_code != 200 or not opps.json().get("items"):
            pytest.skip("No opportunities in database")

        opp_id = opps.json()["items"][0]["id"]

        with patch("app.workers.profile.tasks.schedule_debounced_rerank") as mock_schedule:
            with patch("app.services.ranking.rank_opportunities_for_user") as mock_rank:
                resp = await client.patch(
                    f"/api/v1/opportunities/{opp_id}/status",
                    headers=headers,
                    json={"status": "saved"},
                )
                assert resp.status_code == 200
                body = resp.json()
                assert body["status"] == "saved"
                assert body.get("status_history")
                mock_schedule.assert_called_once()
                mock_rank.assert_not_called()


@pytest.mark.asyncio
async def test_patch_dismiss_requires_reason():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@localhost", "password": "admin"},
        )
        if login.status_code != 200:
            pytest.skip("No seeded admin user for API status test")

        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        opps = await client.get("/api/v1/opportunities?limit=1", headers=headers)
        if opps.status_code != 200 or not opps.json().get("items"):
            pytest.skip("No opportunities in database")

        opp_id = opps.json()["items"][0]["id"]

        resp = await client.patch(
            f"/api/v1/opportunities/{opp_id}/status",
            headers=headers,
            json={"status": "dismissed"},
        )
        assert resp.status_code == 422

        resp_ok = await client.patch(
            f"/api/v1/opportunities/{opp_id}/status",
            headers=headers,
            json={"status": "dismissed", "dismiss_reason": "wrong_field"},
        )
        assert resp_ok.status_code == 200
        assert resp_ok.json()["status"] == "dismissed"
        assert resp_ok.json()["dismiss_reason"] == "wrong_field"

        # Restore so repeated test runs do not pollute matches bucket.
        await client.patch(
            f"/api/v1/opportunities/{opp_id}/status",
            headers=headers,
            json={"status": "new"},
        )
