"""itc-033 (DEC-SCOPE-357) C1-C3 -- the self-only "phone calls" preference on /account/notification-preferences: allowed by default,
an optional `calls` in the body (omitted = unchanged), no phone needed, audited before/after, in the data export, and shown read-only to
the student's itc-003 counselor and the IT Admin on the IT student record."""

import pytest
from sqlalchemy import select

from app.api.account import _build_export
from app.models import AuditLog, ItStudentCounselor, NotificationPreference
from tests.enh014_helpers import login, make_user, set_prefs
from tests.tel018_helpers import as_user, make_counselor, make_student

pytestmark = pytest.mark.asyncio

URL = "/api/v1/account/notification-preferences"


async def audits(db, user) -> list[dict]:
    rows = await db.scalars(select(AuditLog).where(AuditLog.action == "notification_preference.update", AuditLog.user_id == user.id).order_by(AuditLog.created_at))
    return [r.metadata_json for r in rows]


async def test_calls_are_allowed_by_default_without_a_row(client, db_session):
    user = await make_user(db_session)
    await login(client, user.email)
    assert (await client.get(URL)).json() == {"whatsapp": False, "sms": False, "calls": True, "phone_valid": False}


async def test_turning_calls_off_needs_no_phone_is_stamped_and_audited(client, db_session):
    user = await make_user(db_session)  # no phone at all
    await login(client, user.email)
    off = await client.put(URL, json={"whatsapp": False, "sms": False, "calls": False})
    assert off.status_code == 200, off.text
    assert off.json() == {"whatsapp": False, "sms": False, "calls": False, "phone_valid": False}
    row = await db_session.scalar(select(NotificationPreference).where(NotificationPreference.user_id == user.id).execution_options(populate_existing=True))
    assert row.calls_opt_out is True and row.calls_opted_out_at is not None
    assert (await audits(db_session, user))[-1]["before"] == {"whatsapp": False, "sms": False, "calls": True}
    assert (await audits(db_session, user))[-1]["after"] == {"whatsapp": False, "sms": False, "calls": False}

    on = await client.put(URL, json={"whatsapp": False, "sms": False, "calls": True})
    assert on.json()["calls"] is True
    await db_session.refresh(row)
    assert row.calls_opt_out is False and row.calls_opted_out_at is None


async def test_a_body_without_calls_leaves_it_unchanged(client, db_session):
    user = await make_user(db_session, phone="98765 43210")
    await login(client, user.email)
    await client.put(URL, json={"whatsapp": False, "sms": False, "calls": False})
    stamped = await db_session.scalar(select(NotificationPreference.calls_opted_out_at).where(NotificationPreference.user_id == user.id))
    response = await client.put(URL, json={"whatsapp": True, "sms": False})
    assert response.status_code == 200
    assert response.json() == {"whatsapp": True, "sms": False, "calls": False, "phone_valid": True}
    # the opt-out timestamp is the consent evidence: an unrelated save keeps it
    assert await db_session.scalar(select(NotificationPreference.calls_opted_out_at).where(NotificationPreference.user_id == user.id).execution_options(populate_existing=True)) == stamped


async def test_an_existing_whatsapp_row_reads_calls_allowed_and_no_change_writes_no_audit(client, db_session):
    user = await make_user(db_session, phone="98765 43210")
    await set_prefs(db_session, user, whatsapp=True)
    await login(client, user.email)
    assert (await client.get(URL)).json()["calls"] is True
    await client.put(URL, json={"whatsapp": True, "sms": False, "calls": True})
    assert await audits(db_session, user) == []


@pytest.mark.parametrize("body", [{"whatsapp": False, "sms": False, "calls": "no"}, {"whatsapp": False, "sms": False, "calls": 0}, {"whatsapp": False, "sms": False, "calls": False, "user_id": "x"}])
async def test_invalid_calls_values_and_extra_fields_are_422(client, db_session, body):
    user = await make_user(db_session)
    await login(client, user.email)
    assert (await client.put(URL, json=body)).status_code == 422


async def test_the_export_carries_the_call_preference(client, db_session):
    user = await make_user(db_session)
    assert (await _build_export(db_session, user))["notification_preferences"]["calls"] is True
    await login(client, user.email)
    await client.put(URL, json={"whatsapp": False, "sms": False, "calls": False})
    prefs = (await _build_export(db_session, user))["notification_preferences"]
    assert prefs["calls"] is False and prefs["calls_opted_out_at"]


async def test_the_linked_counselor_and_the_it_admin_see_the_opt_out(client, db_session):
    counselor = await make_counselor(db_session, "it")
    student = await make_student(db_session)
    db_session.add(ItStudentCounselor(student_user_id=student.id, counselor_user_id=counselor.id, assigned_by_user_id=counselor.id))
    await db_session.commit()
    admin = await make_user(db_session, role="it_admin", division="it")

    await as_user(client, counselor)
    assert (await client.get(f"/api/v1/counselor/it/students/{student.id}/profile")).json()["student"]["calls_allowed"] is True

    db_session.add(NotificationPreference(user_id=student.id, calls_opt_out=True))
    await db_session.commit()
    assert (await client.get(f"/api/v1/counselor/it/students/{student.id}/profile")).json()["student"]["calls_allowed"] is False
    await login(client, admin.email, division="it")
    assert (await client.get(f"/api/v1/admin/it/students/{student.id}/profile")).json()["student"]["calls_allowed"] is False
