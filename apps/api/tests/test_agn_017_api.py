"""AGN-017 AC8 -- the unread count is the caller's own; the existing list/read contracts are unchanged (no dedupe_key, newest first,
404 for another user's notification)."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models import Notification
from tests.agn001_helpers import client_for, mk_user
from tests.agn008_helpers import agency_world

BASE = "/api/v1/workflows/notifications"
LIST_KEYS = {"id", "title", "body", "read", "action_url", "created_at"}


@pytest_asyncio.fixture
async def world(db_session):
    w = await agency_world(db_session)
    staff, master = w["staff"]["user"], w["master"]
    rows = [
        Notification(user_id=staff.id, title="A", body="a", read=False, action_url="/overseas/agent/tasks", dedupe_key="agn017:test:a:" + str(staff.id)),
        Notification(user_id=staff.id, title="B", body="b", read=False),
        Notification(user_id=staff.id, title="C", body="c", read=True),
        Notification(user_id=master.id, title="M", body="m", read=False),
    ]
    db_session.add_all(rows)
    await db_session.commit()
    return w | {"rows": rows}


@pytest.mark.asyncio
async def test_unread_count_is_the_callers_own(db_session, world):
    async with client_for(world["staff"]["user"].email) as c:
        response = await c.get(f"{BASE}/unread-count")
    assert response.status_code == 200, response.text
    assert response.json() == {"unread": 2}


@pytest.mark.asyncio
async def test_reading_one_lowers_the_count(db_session, world):
    async with client_for(world["staff"]["user"].email) as c:
        assert (await c.patch(f"{BASE}/{world['rows'][0].id}/read")).json() == {"ok": True}
        assert (await c.get(f"{BASE}/unread-count")).json() == {"unread": 1}


@pytest.mark.asyncio
async def test_unread_count_needs_a_session():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.get(f"{BASE}/unread-count")).status_code == 401


@pytest.mark.asyncio
async def test_the_list_contract_is_unchanged_and_never_shows_the_dedupe_key(db_session, world):
    async with client_for(world["staff"]["user"].email) as c:
        items = (await c.get(BASE)).json()
    assert isinstance(items, list) and len(items) == 3
    assert all(set(item) == LIST_KEYS for item in items)


@pytest.mark.parametrize("who", ["master", "staff"])
@pytest.mark.asyncio
async def test_the_agency_notifications_page_has_a_header_payload_for_masters_and_staff(db_session, world, who):
    user = world["master"] if who == "master" else world["staff"]["user"]
    async with client_for(user.email) as c:
        response = await c.get("/api/v1/portal/overseas/agent/notifications")
    assert response.status_code == 200, response.text
    assert response.json()["title"] == "Notifications"


@pytest.mark.asyncio
async def test_the_agency_notifications_page_still_refuses_another_role(db_session, world):
    counselor = await mk_user(db_session, role="counselor", full_name="Not An Agent")
    async with client_for(counselor.email) as c:
        assert (await c.get("/api/v1/portal/overseas/agent/notifications")).status_code == 403


@pytest.mark.asyncio
async def test_reading_another_users_notification_is_not_found(db_session, world):
    async with client_for(world["staff"]["user"].email) as c:
        assert (await c.patch(f"{BASE}/{world['rows'][3].id}/read")).status_code == 404
    async with client_for(world["master"].email) as c:
        assert (await c.get(f"{BASE}/unread-count")).json() == {"unread": 1}
