"""ENH-014 Task 9 -- erasure deletes preferences; export includes them (AC13)."""

import uuid

import pytest

from app.api.account import _build_export
from app.models import NotificationPreference
from tests.enh014_helpers import login, make_user, set_prefs


async def _request_and_fulfil_erasure(client, db_session, user) -> None:
    await login(client, user.email, division="it")
    created = await client.post("/api/v1/account/data-requests", json={"type": "delete"}, headers={"Idempotency-Key": uuid.uuid4().hex})
    assert created.status_code in (201, 202), created.text
    admin = await make_user(db_session, role="it_admin", division="it")
    await login(client, admin.email, division="it")
    response = await client.patch(f"/api/v1/admin/data-requests/{created.json()['id']}", json={"decision": "fulfil"})
    assert response.status_code == 200 and response.json()["status"] == "fulfilled", response.text


@pytest.mark.asyncio
async def test_export_includes_notification_preferences(db_session):
    user = await make_user(db_session, phone="9876543210")
    await set_prefs(db_session, user, whatsapp=True)
    exported = await _build_export(db_session, user)
    prefs = exported["notification_preferences"]
    assert (prefs["whatsapp"], prefs["sms"], prefs["sms_opted_in_at"]) == (True, False, None) and prefs["whatsapp_opted_in_at"]


@pytest.mark.asyncio
async def test_export_without_a_row_reports_both_off(db_session):
    user = await make_user(db_session)
    assert (await _build_export(db_session, user))["notification_preferences"] == {"whatsapp": False, "sms": False, "whatsapp_opted_in_at": None, "sms_opted_in_at": None}


@pytest.mark.asyncio
async def test_fulfilled_erasure_deletes_the_preference_row(client, db_session):
    user = await make_user(db_session, role="it_student", division="it", phone="9876543210")
    await set_prefs(db_session, user, sms=True)
    await _request_and_fulfil_erasure(client, db_session, user)
    assert await db_session.get(NotificationPreference, user.id, populate_existing=True) is None
