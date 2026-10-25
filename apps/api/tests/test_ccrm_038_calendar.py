"""ccrm-038 (DEC-SCOPE-272 CA1-CA8; API §12FY; RBAC §2.186): `.ics` invites on appointment emails and the counselor's read-only iCal feed.
The shared test database is never truncated: every builder makes its own users."""

import uuid
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models import Appointment, AuditLog, CalendarFeed, Notification, NotificationDelivery, VisaCase
from app.services import calendar_ics, mailer
from tests.agn001_helpers import mk_user, uniq
from tests.agn008_helpers import mk_application
from tests.ccrm012_helpers import mk_university
from tests.enh014_helpers import drain
from tests.tel016_helpers import action_url, as_user, at, book, setup

FEED_API = "/api/v1/counselor/calendar-feed"


def feed_path(url: str) -> str:
    return url[url.index("/api/v1/"):]


async def deliveries(db, user) -> list[NotificationDelivery]:
    rows = await db.scalars(
        select(NotificationDelivery).join(Notification, Notification.id == NotificationDelivery.notification_id)
        .where(Notification.user_id == user.id, NotificationDelivery.channel == "email").order_by(NotificationDelivery.created_at)
    )
    return [r for r in rows.all() if (r.context or {}).get("kind") == "appointment_invite"]


@pytest.fixture
def outbox(monkeypatch):
    monkeypatch.setattr(settings, "email_transport", "smtp")
    monkeypatch.setattr(settings, "smtp_host", "smtp.test.local")
    monkeypatch.setattr(settings, "smtp_from_email", "noreply@edusphere.local")
    sent = []
    monkeypatch.setattr(mailer, "_send_sync", sent.append)
    return sent


# --- calendar_ics (CA2, security: escaping) ------------------------------------------------------------------------------------------
def test_ics_escapes_text_and_folds_long_lines():
    start = datetime(2026, 11, 3, 4, 30, tzinfo=UTC)
    text = calendar_ics.calendar(
        [calendar_ics.event(uid="u1@edusphere", sequence=2, start=start, end=start + timedelta(hours=1), summary="A; B, C\\D\r\nX:INJECT",
                            location="x" * 120)],
        method="REQUEST",
    )
    assert text.startswith("BEGIN:VCALENDAR\r\n") and text.endswith("END:VCALENDAR\r\n")
    assert "METHOD:REQUEST\r\n" in text and "SEQUENCE:2\r\n" in text and "DTSTART:20261103T043000Z\r\n" in text
    assert "SUMMARY:A\\; B\\, C\\\\D\\nX:INJECT\r\n" in text
    assert "\r\nX:INJECT" not in text  # no new property can be injected
    assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))
    assert "\r\n " in text  # the long LOCATION is folded


def test_ics_all_day_event_and_no_method_for_a_feed():
    text = calendar_ics.calendar([calendar_ics.all_day_event(uid="v1@edusphere", day=date(2026, 12, 1), summary="Visa appointment")])
    assert "METHOD" not in text
    assert "DTSTART;VALUE=DATE:20261201\r\n" in text and "DTEND;VALUE=DATE:20261202\r\n" in text


# --- CA1/CA2: lead appointment invites (counselor only) ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_lead_booking_reschedule_and_cancel_queue_invites_for_the_counselor(client, db_session):
    _, tel, counselor, lead = await setup(db_session, "overseas")
    out = (await book(client, tel, lead, counselor)).json()
    rows = await deliveries(db_session, counselor)
    assert len(rows) == 1
    ics = rows[0].context["ics"]
    assert rows[0].context["method"] == "REQUEST" and "METHOD:REQUEST" in ics and "SEQUENCE:0" in ics
    assert f"UID:appointment-{out['id']}@edusphere" in ics and "Course fit" not in ics  # never the purpose (CA2)
    await as_user(client, counselor)
    assert (await client.post(action_url(out["id"], "confirm"))).status_code == 200
    assert len(await deliveries(db_session, counselor)) == 1  # a confirmation sends nothing
    assert (await client.post(action_url(out["id"], "reschedule"), json={"scheduled_at": at(days=3)})).status_code == 200
    assert (await client.post(action_url(out["id"], "cancel"), json={"reason": "Lead travelling"})).status_code == 200
    rows = await deliveries(db_session, counselor)
    assert [r.context["method"] for r in rows] == ["REQUEST", "REQUEST", "CANCEL"]
    assert "SEQUENCE:1" in rows[1].context["ics"] and "SEQUENCE:2" in rows[2].context["ics"] and "STATUS:CANCELLED" in rows[2].context["ics"]
    assert await deliveries(db_session, tel) == []  # the telecaller is not an attendee
    note = await db_session.scalar(select(Notification).where(Notification.id == rows[0].notification_id))
    assert note.title == "Counselling appointment booked" and note.action_url == "/overseas/counselor/appointments"


@pytest.mark.asyncio
async def test_an_it_lead_booking_sends_no_invite(client, db_session):
    _, tel, counselor, lead = await setup(db_session, "it")
    assert (await book(client, tel, lead, counselor)).status_code == 201
    assert await deliveries(db_session, counselor) == []


# --- CA1: student appointment invites (student + counselor) --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_student_appointment_invites_the_student_and_the_counselor(client, db_session, outbox, enqueued):
    from tests.agn001_helpers import login

    counselor = await mk_user(db_session, role="counselor", full_name=f"Cal Counselor {uniq()}")
    student = await mk_user(db_session, role="overseas_student", full_name=f"Cal Student {uniq()}")
    await login(client, student.email)
    response = await client.post("/api/v1/workflows/overseas/appointments", json={"staff_id": str(counselor.id), "scheduled_at": at(days=2)})
    assert response.status_code == 201, response.text
    appt_id = response.json()["id"]
    assert [r.context["method"] for r in await deliveries(db_session, student)] == ["REQUEST"]
    assert [r.context["method"] for r in await deliveries(db_session, counselor)] == ["REQUEST"]

    await drain(enqueued)
    invites = [m for m in outbox if m["To"] in (student.email, counselor.email)]
    assert len(invites) == 2
    attachment = next(invites[0].iter_attachments())
    assert attachment.get_filename() == "invite.ics" and attachment.get_content_type() == "text/calendar"
    assert attachment.get_param("method") == "REQUEST" and f"UID:appointment-{appt_id}@edusphere" in attachment.get_content()

    client.cookies.clear()
    await login(client, counselor.email)
    url = f"/api/v1/workflows/overseas/appointments/{appt_id}"
    assert (await client.patch(url, json={"mode": "Phone"})).status_code == 200  # no time/cancel change: nothing
    assert (await client.patch(url, json={"scheduled_at": at(days=4)})).status_code == 200
    assert (await client.patch(url, json={"status": "cancelled"})).status_code == 200
    assert [r.context["method"] for r in await deliveries(db_session, student)] == ["REQUEST", "REQUEST", "CANCEL"]
    row = await db_session.get(Appointment, uuid.UUID(appt_id), populate_existing=True)
    assert row.calendar_sequence == 2


@pytest.mark.asyncio
async def test_an_appointment_without_a_counselor_invites_only_the_student(client, db_session):
    from tests.agn001_helpers import login

    student = await mk_user(db_session, role="overseas_student", full_name=f"Cal Student {uniq()}")
    await login(client, student.email)
    assert (await client.post("/api/v1/workflows/overseas/appointments", json={"scheduled_at": at(days=2)})).status_code == 201
    assert len(await deliveries(db_session, student)) == 1


# --- CA3: the Zoho Mail API transport uploads the attachment ------------------------------------------------------------------------
def test_zoho_uploads_the_invite_and_references_it(monkeypatch):
    from app.services import zoho_mail

    zoho_mail.reset_token_cache()
    monkeypatch.setattr(settings, "email_transport", "zoho_api")
    monkeypatch.setattr(settings, "smtp_from_email", "noreply@example.local")
    for name in ("zoho_mail_client_id", "zoho_mail_client_secret", "zoho_mail_refresh_token"):
        monkeypatch.setattr(settings, name, f"{name}-value")
    monkeypatch.setattr(settings, "zoho_mail_account_id", "acct42")
    monkeypatch.setattr(settings, "zoho_mail_api_base", "https://mail.zoho.test")
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/oauth/v2/token":
            return httpx.Response(200, json={"access_token": "tok1", "expires_in": 3600})
        if request.url.path.endswith("/messages/attachments"):
            return httpx.Response(200, json={"status": {"code": 200}, "data": {"storeName": "S1", "attachmentPath": "/p/1", "attachmentName": "invite.ics"}})
        return httpx.Response(200, json={"status": {"code": 200}})

    msg = mailer.generic_notification_message(to_email="s@example.local", recipient_name="S", title="T", body="B", action_url=None,
                                              ics="BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n", ics_method="REQUEST")
    zoho_mail.send(msg, client=httpx.Client(transport=httpx.MockTransport(handler)))
    upload = next(r for r in seen if r.url.path.endswith("/messages/attachments"))
    assert upload.url.params["fileName"] == "invite.ics" and upload.content == b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"
    assert upload.headers["authorization"] == "Zoho-oauthtoken tok1"
    import json

    send = next(r for r in seen if r.url.path == "/api/accounts/acct42/messages")
    assert json.loads(send.content)["attachments"] == [{"storeName": "S1", "attachmentPath": "/p/1", "attachmentName": "invite.ics"}]
    zoho_mail.reset_token_cache()


def test_zoho_without_attachments_sends_no_upload(monkeypatch):
    from app.services import zoho_mail

    msg = mailer.generic_notification_message(to_email="s@example.local", recipient_name="S", title="T", body="B", action_url=None)
    assert zoho_mail.attachments_of(msg) == []
    assert "attachments" not in zoho_mail.payload_from_message(msg)


# --- CA4/CA7: managing the feed ------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_feed_create_regenerate_revoke(client, db_session):
    from tests.agn001_helpers import login

    counselor = await mk_user(db_session, role="counselor", full_name=f"Feed Counselor {uniq()}")
    await login(client, counselor.email)
    assert (await client.get(FEED_API)).json() == {"active": False, "created_at": None, "url": None}
    created = await client.post(FEED_API)
    assert created.status_code == 201, created.text
    url = created.json()["url"]
    assert url.startswith(settings.frontend_url.rstrip("/") + "/api/v1/calendar/feeds/") and url.endswith(".ics")
    token = url.rsplit("/", 1)[1].removesuffix(".ics")
    assert len(token) >= 43
    status = (await client.get(FEED_API)).json()
    assert status["active"] is True and status["url"] is None  # shown once
    row = await db_session.scalar(select(CalendarFeed).where(CalendarFeed.user_id == counselor.id))
    assert token not in row.token_hash

    assert (await client.get(feed_path(url))).status_code == 200
    regenerated = (await client.post(FEED_API)).json()["url"]
    assert regenerated != url
    assert (await client.get(feed_path(url))).status_code == 404  # the old link stops working
    assert (await client.get(feed_path(regenerated))).status_code == 200
    assert (await client.delete(FEED_API)).status_code == 204
    assert (await client.get(feed_path(regenerated))).status_code == 404
    assert (await client.delete(FEED_API)).status_code == 204  # idempotent
    actions = (await db_session.scalars(select(AuditLog.action).where(AuditLog.user_id == counselor.id, AuditLog.entity_type == "calendar_feed"))).all()
    assert sorted(actions) == ["calendar_feed.create", "calendar_feed.regenerate", "calendar_feed.revoke"]
    logged = (await db_session.scalars(select(AuditLog).where(AuditLog.user_id == counselor.id, AuditLog.entity_type == "calendar_feed"))).all()
    assert all(token not in str(a.metadata_json) for a in logged)


@pytest.mark.asyncio
@pytest.mark.parametrize("role,division", [("overseas_admin", "overseas"), ("overseas_student", "overseas"), ("counselor", "it"), ("telecaller", "overseas")])
async def test_only_an_overseas_counselor_has_a_feed(client, db_session, role, division):
    from tests.agn001_helpers import login

    user = await mk_user(db_session, role=role, division=division)
    await login(client, user.email, division)
    for method in ("get", "post", "delete"):
        assert (await getattr(client, method)(FEED_API)).status_code == 403


@pytest.mark.asyncio
async def test_feed_needs_a_session_to_manage(client):
    client.cookies.clear()
    assert (await client.get(FEED_API)).status_code == 401


# --- CA5/CA6: the feed body ----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_feed_lists_own_appointments_and_counselled_visa_appointments(client, db_session):
    from tests.agn001_helpers import login

    counselor = await mk_user(db_session, role="counselor", full_name=f"Feed Counselor {uniq()}")
    other = await mk_user(db_session, role="counselor", full_name=f"Other Counselor {uniq()}")
    student = await mk_user(db_session, role="overseas_student", full_name=f"Feed Student {uniq()}")
    soon = datetime.now(UTC).replace(microsecond=0) + timedelta(days=2)
    mine = Appointment(division="overseas", student_id=student.id, staff_id=counselor.id, scheduled_at=soon, appointment_type="Career Counseling", mode="Online", status="scheduled")
    cancelled = Appointment(division="overseas", student_id=student.id, staff_id=counselor.id, scheduled_at=soon, appointment_type="Career Counseling", mode="Online", status="cancelled")
    old = Appointment(division="overseas", student_id=student.id, staff_id=counselor.id, scheduled_at=soon - timedelta(days=200), appointment_type="Career Counseling", mode="Online", status="completed")
    theirs = Appointment(division="overseas", student_id=student.id, staff_id=other.id, scheduled_at=soon, appointment_type="Career Counseling", mode="Online", status="scheduled")
    db_session.add_all([mine, cancelled, old, theirs])
    university = await mk_university(db_session, "Feedland")
    app = await mk_application(db_session, agent=None, university=university, student=student, counselor_id=counselor.id, status="visa_processing")
    other_app = await mk_application(db_session, agent=None, university=university, student=student, counselor_id=other.id, status="visa_processing")
    visa = VisaCase(application_id=app.id, appointment_date=date.today() + timedelta(days=10), appointment_place="VFS Chennai",
                    refusal_reason="SECRET-REASON")
    other_visa = VisaCase(application_id=other_app.id, appointment_date=date.today() + timedelta(days=10))
    db_session.add_all([visa, other_visa])
    await db_session.commit()

    await login(client, counselor.email)
    url = (await client.post(FEED_API)).json()["url"]
    client.cookies.clear()  # the feed needs no session
    response = await client.get(feed_path(url))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/calendar")
    assert "no-store" in response.headers["cache-control"]
    body = response.text
    assert f"UID:appointment-{mine.id}@edusphere" in body
    assert f"appointment-{cancelled.id}" not in body and f"appointment-{old.id}" not in body and f"appointment-{theirs.id}" not in body
    assert f"UID:visa-{visa.id}@edusphere" in body and f"visa-{other_visa.id}" not in body
    assert "VFS Chennai" in body and "SECRET-REASON" not in body and "METHOD" not in body
    assert student.full_name in body


@pytest.mark.asyncio
async def test_a_deactivated_counselor_feed_is_gone(client, db_session):
    from tests.agn001_helpers import login

    counselor = await mk_user(db_session, role="counselor", full_name=f"Feed Counselor {uniq()}")
    await login(client, counselor.email)
    url = (await client.post(FEED_API)).json()["url"]
    counselor.active = False
    db_session.add(counselor)
    await db_session.commit()
    assert (await client.get(feed_path(url))).status_code == 404
    assert (await client.get("/api/v1/calendar/feeds/not-a-real-token.ics")).status_code == 404
