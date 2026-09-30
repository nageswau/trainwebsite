"""ENH-014 Task 3 -- GET/PUT /account/notification-preferences (spec §5.1-5.2; AC01-AC03, AC15)."""

import asyncio

import pytest
from sqlalchemy import select

from app.models import AuditLog, NotificationPreference
from tests.enh014_helpers import login, make_user, set_prefs

URL = "/api/v1/account/notification-preferences"


@pytest.mark.asyncio
async def test_both_routes_require_a_session(client):
    assert (await client.get(URL)).status_code == 401
    assert (await client.put(URL, json={"whatsapp": False, "sms": False})).status_code == 401


@pytest.mark.asyncio
async def test_defaults_are_off_and_phone_validity_is_reported(client, db_session):
    user = await make_user(db_session, phone="98765 43210")
    await login(client, user.email)
    response = await client.get(URL)
    assert response.status_code == 200
    assert response.json() == {"whatsapp": False, "sms": False, "phone_valid": True}


@pytest.mark.asyncio
async def test_turning_on_without_a_valid_phone_is_422_and_writes_nothing(client, db_session):
    user = await make_user(db_session, phone="12345")
    await login(client, user.email)
    response = await client.put(URL, json={"whatsapp": True, "sms": False})
    assert response.status_code == 422
    assert response.json() == {"detail": "Add a valid mobile number to your profile first"}
    assert await db_session.get(NotificationPreference, user.id) is None


@pytest.mark.asyncio
async def test_turning_off_is_allowed_without_a_phone(client, db_session):
    # Review Focus 2: opted in, then cleared the phone -- turning channels off must still work.
    user = await make_user(db_session, phone=None)
    await set_prefs(db_session, user, whatsapp=True, sms=True)
    await login(client, user.email)
    response = await client.put(URL, json={"whatsapp": True, "sms": False})  # WhatsApp unchanged, SMS off
    assert response.status_code == 200, response.text
    assert response.json() == {"whatsapp": True, "sms": False, "phone_valid": False}


@pytest.mark.asyncio
async def test_opt_in_and_out_set_and_clear_timestamps_and_audit_once(client, db_session):
    user = await make_user(db_session, phone="+91 98765 43210")
    await login(client, user.email)
    on = await client.put(URL, json={"whatsapp": True, "sms": False})
    assert on.status_code == 200 and on.json() == {"whatsapp": True, "sms": False, "phone_valid": True}
    pref = await db_session.get(NotificationPreference, user.id, populate_existing=True)
    first_opt_in = pref.whatsapp_opted_in_at
    assert first_opt_in is not None and pref.sms_opted_in_at is None

    again = await client.put(URL, json={"whatsapp": True, "sms": False})  # no change: timestamp kept, no audit
    assert again.status_code == 200
    pref = await db_session.get(NotificationPreference, user.id, populate_existing=True)
    assert pref.whatsapp_opted_in_at == first_opt_in

    off = await client.put(URL, json={"whatsapp": False, "sms": False})
    assert off.status_code == 200
    pref = await db_session.get(NotificationPreference, user.id, populate_existing=True)
    assert pref.whatsapp_opt_in is False and pref.whatsapp_opted_in_at is None

    audits = (await db_session.scalars(select(AuditLog).where(AuditLog.user_id == user.id, AuditLog.action == "notification_preference.update").order_by(AuditLog.created_at))).all()
    assert [a.metadata_json for a in audits] == [
        {"before": {"whatsapp": False, "sms": False}, "after": {"whatsapp": True, "sms": False}, "consent_text": "enh014-v1"},
        {"before": {"whatsapp": True, "sms": False}, "after": {"whatsapp": False, "sms": False}, "consent_text": "enh014-v1"},
    ]
    assert all("98765" not in str(a.metadata_json) for a in audits)


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{"whatsapp": "yes", "sms": False}, {"whatsapp": 1, "sms": False}, {"whatsapp": True}, {"whatsapp": False, "sms": False, "user_id": "x"}, {"whatsapp": False, "sms": False, "whatsapp_opted_in_at": "2020-01-01T00:00:00Z"}])
async def test_only_two_strict_booleans_are_accepted(client, db_session, body):
    user = await make_user(db_session, phone="9876543210")
    await login(client, user.email)
    assert (await client.put(URL, json=body)).status_code == 422
    assert await db_session.get(NotificationPreference, user.id) is None


@pytest.mark.asyncio
async def test_a_user_changes_only_their_own_row(client, db_session):
    other = await make_user(db_session, phone="9876543210")
    await set_prefs(db_session, other, whatsapp=True)
    me = await make_user(db_session, phone="9876543211")
    await login(client, me.email)
    assert (await client.put(URL, json={"whatsapp": False, "sms": True})).status_code == 200
    theirs = await db_session.get(NotificationPreference, other.id, populate_existing=True)
    assert (theirs.whatsapp_opt_in, theirs.sms_opt_in) == (True, False)


@pytest.mark.asyncio
async def test_concurrent_saves_leave_exactly_one_row(client, db_session):
    user = await make_user(db_session, phone="9876543210")
    await login(client, user.email)
    responses = await asyncio.gather(*(client.put(URL, json={"whatsapp": i % 2 == 0, "sms": True}) for i in range(6)))
    assert all(r.status_code == 200 for r in responses)
    rows = (await db_session.scalars(select(NotificationPreference).where(NotificationPreference.user_id == user.id))).all()
    assert len(rows) == 1
