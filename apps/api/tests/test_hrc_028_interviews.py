"""hrc-028 -- interview completion (DEC-SCOPE-400 I1-I9; AC1-AC6): the new fields, the link/location history, cancel, the duration kept on a
reschedule, the notices with their calendar invite, the time zone and the student portal. The shared test database is never truncated, so
every value is unique per test."""

from datetime import UTC, datetime, timedelta
from email import message_from_bytes

import pytest
from sqlalchemy import select

from app.models import AuditLog, InterviewEvent, Notification, NotificationDelivery, RecruiterMessage
from app.notifications import recruiter_email
from app.services import interviews as svc
from app.services import mailer
from tests.rec001_helpers import login, make_user
from tests.rec017_helpers import student_application
from tests.test_rec_017_tracking import _requirement, _team
from tests.test_rec_020_interviews import INTERVIEWS, _app_status, _at, _interview, _move, _schedule, _setup, _to_past, published, smtp_on  # noqa: F401

PORTAL = "/api/v1/portal/it/student/interview-schedule"


def _ends(start_iso: str, minutes: int) -> str:
    start = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
    return (start + timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z")


async def _student_setup(client, db):
    _, recruiter = await _team(client, db)
    job = await _requirement(db, recruiter)
    student = await make_user(db, "it_student", "it")
    application = await student_application(db, job.id, student, status="shortlisted")
    await db.commit()
    return recruiter, student, application


async def _invites(db, student) -> list[NotificationDelivery]:
    rows = await db.scalars(
        select(NotificationDelivery)
        .join(Notification, Notification.id == NotificationDelivery.notification_id)
        .where(Notification.user_id == student.id, NotificationDelivery.channel == "email")
        .order_by(NotificationDelivery.created_at)
    )
    return [r for r in rows.all() if (r.context or {}).get("kind") == "interview_invite"]


async def _portal_rows(client, student) -> list[dict]:
    await login(client, student)
    response = await client.get(PORTAL)
    assert response.status_code == 200, response.text
    return response.json()["rows"]


# --- I1: the fields -----------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_schedule_takes_and_returns_the_new_fields(client, db_session):
    s = await _setup(client, db_session)
    start = _at(3)
    item = await _interview(
        client,
        s["application"]["id"],
        scheduled_at=start,
        ends_at=_ends(start, 45),
        round_number=2,
        time_zone="Asia/Dubai",
        platform="google_meet",
        phone_details="+91 98450 00000 ext 4",
        instructions="Bring a pen.\nArrive early.",
        documents_required="ID proof\nResume",
    )
    assert (item["round_number"], item["time_zone"], item["platform"], item["platform_label"]) == (2, "Asia/Dubai", "google_meet", "Google Meet")
    assert item["ends_at"].startswith(_ends(start, 45)[:16]) and item["instructions"] == "Bring a pen.\nArrive early."
    assert (item["phone_details"], item["documents_required"], item["cancel_reason"]) == ("+91 98450 00000 ext 4", "ID proof\nResume", None)


@pytest.mark.asyncio
async def test_defaults_keep_legacy_payloads_working(client, db_session):
    s = await _setup(client, db_session)
    item = await _interview(client, s["application"]["id"])
    assert (item["time_zone"], item["ends_at"], item["round_number"], item["platform"]) == ("Asia/Kolkata", None, None, None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("over", "field"),
    [
        ({"time_zone": "Mars/Base"}, "time_zone"),
        ({"time_zone": "../etc/passwd"}, "time_zone"),
        ({"platform": "skype"}, "platform"),
        ({"round_number": 0}, "round_number"),
        ({"round_number": 21}, "round_number"),
        ({"instructions": "x" * 2001}, "instructions"),
    ],
)
async def test_invalid_fields_are_422_on_their_field(client, db_session, over, field):
    s = await _setup(client, db_session)
    response = await _schedule(client, s["application"]["id"], **over)
    assert response.status_code == 422 and field in str(response.json()["detail"][0]["loc"])


@pytest.mark.asyncio
@pytest.mark.parametrize("minutes", [0, -30, 12 * 60 + 1])
async def test_the_end_must_follow_the_start_within_12_hours(client, db_session, minutes):
    s = await _setup(client, db_session)
    start = _at(3)
    response = await _schedule(client, s["application"]["id"], scheduled_at=start, ends_at=_ends(start, minutes))
    assert response.status_code == 422 and response.json()["detail"][0]["loc"][-1] == "ends_at"


# --- I4 / AC1: link history ---------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_link_change_keeps_the_old_link_on_a_details_event_and_the_portal_shows_only_the_new_one(client, db_session):
    recruiter, student, application = await _student_setup(client, db_session)
    item = await _interview(client, application.id, meeting_url="https://meet.example.com/old-link")
    response = await client.patch(f"{INTERVIEWS}/{item['id']}", json={"meeting_url": "https://meet.example.com/new-link", "location": "Room 4", "notify": False})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["meeting_url"] == "https://meet.example.com/new-link" and "notifications" not in body
    details = [h for h in body["history"] if h["event"] == "details"]
    assert len(details) == 1 and details[0]["old_meeting_url"] == "https://meet.example.com/old-link"
    assert (details[0]["new_meeting_url"], details[0]["old_location"], details[0]["new_location"]) == ("https://meet.example.com/new-link", None, "Room 4")
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "recruiter_interview.update", AuditLog.entity_id == item["id"]))
    assert "old-link" not in str(audit.metadata_json)  # hrc-004 keeps redacting the URL
    rows = await _portal_rows(client, student)
    row = next(r for r in rows if r["round"].startswith("HR Round"))
    assert row["link"] == "https://meet.example.com/new-link" and "old-link" not in str(rows)
    await login(client, recruiter)


@pytest.mark.asyncio
async def test_a_patch_without_a_link_change_writes_no_details_event(client, db_session):
    s = await _setup(client, db_session)
    item = await _interview(client, s["application"]["id"])
    response = await client.patch(f"{INTERVIEWS}/{item['id']}", json={"interviewer": "Meera", "round_number": 3, "notify": False})
    assert response.status_code == 200 and response.json()["round_number"] == 3
    assert not [h for h in response.json()["history"] if h["event"] == "details"]


# --- I3 / AC2 / AC5: cancel ---------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cancel_records_the_reason_and_closes_the_interview(client, db_session):
    s = await _setup(client, db_session)
    item = await _interview(client, s["application"]["id"])
    response = await client.post(f"{INTERVIEWS}/{item['id']}/cancel", json={"reason": "Panel unavailable", "notify": False})
    assert response.status_code == 200, response.text
    out = response.json()["interview"]
    assert (out["status"], out["status_label"], out["cancel_reason"]) == ("cancelled", "Cancelled", "Panel unavailable")
    assert (out["can_edit"], out["can_reschedule"], out["allowed_statuses"], out["can_cancel"]) == (False, False, [], False)
    assert (out["history"][-1]["event"], out["history"][-1]["to_status"], out["history"][-1]["note"]) == ("status", "cancelled", "Panel unavailable")
    assert response.json()["notifications"] == {"candidate": "off", "contact": None}
    assert await _app_status(db_session, s["application"]["id"]) == "interview"  # I3: the application does not move
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "recruiter_interview.cancel", AuditLog.entity_id == item["id"]))
    assert audit is not None and "Panel" not in str(audit.metadata_json)
    closed = (await client.get(INTERVIEWS, params={"view": "closed"})).json()
    assert item["id"] in [i["id"] for i in closed["items"]]
    for method, path, body in (
        ("patch", "", {"interviewer": "X"}),
        ("post", "/reschedule", {"scheduled_at": _at(5)}),
        ("post", "/status", {"status": "confirmed"}),
        ("post", "/cancel", {"reason": "Again"}),
    ):
        refused = await getattr(client, method)(f"{INTERVIEWS}/{item['id']}{path}", json=body)
        assert refused.status_code == 409, (path, refused.text)


@pytest.mark.asyncio
async def test_a_cancelled_slot_no_longer_clashes(client, db_session):
    s = await _setup(client, db_session)
    when = _at(4)
    item = await _interview(client, s["application"]["id"], scheduled_at=when)
    assert (await client.post(f"{INTERVIEWS}/{item['id']}/cancel", json={"reason": "Moved", "notify": False})).status_code == 200
    assert (await _schedule(client, s["application"]["id"], scheduled_at=when)).status_code == 201


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{}, {"reason": ""}, {"reason": "   "}, {"reason": "x" * 501}])
async def test_cancel_needs_a_reason(client, db_session, body):
    s = await _setup(client, db_session)
    item = await _interview(client, s["application"]["id"])
    response = await client.post(f"{INTERVIEWS}/{item['id']}/cancel", json=body)
    assert response.status_code == 422 and response.json()["detail"][0]["loc"][-1] == "reason"


@pytest.mark.asyncio
async def test_a_completed_or_decided_interview_cannot_be_cancelled(client, db_session):
    s = await _setup(client, db_session)
    item = await _interview(client, s["application"]["id"])
    await _to_past(db_session, item["id"])
    assert (await _move(client, item["id"], "completed")).status_code == 200
    response = await client.post(f"{INTERVIEWS}/{item['id']}/cancel", json={"reason": "Too late"})
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_an_on_hold_interview_can_be_cancelled(client, db_session):
    s = await _setup(client, db_session)
    item = await _interview(client, s["application"]["id"])
    assert (await _move(client, item["id"], "on_hold")).status_code == 200
    assert (await client.post(f"{INTERVIEWS}/{item['id']}/cancel", json={"reason": "Role paused", "notify": False})).status_code == 200


# --- I2: reschedule keeps the duration ----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_reschedule_keeps_the_duration_and_the_past_stays_422(client, db_session):
    s = await _setup(client, db_session)
    start = _at(3)
    item = await _interview(client, s["application"]["id"], scheduled_at=start, ends_at=_ends(start, 90))
    new = _at(6, minute=30)
    out = (await client.post(f"{INTERVIEWS}/{item['id']}/reschedule", json={"scheduled_at": new, "notify": False})).json()["interview"]
    assert datetime.fromisoformat(out["ends_at"]) - datetime.fromisoformat(out["scheduled_at"]) == timedelta(minutes=90)
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    assert (await client.post(f"{INTERVIEWS}/{item['id']}/reschedule", json={"scheduled_at": past})).status_code == 422


@pytest.mark.asyncio
async def test_a_patched_end_must_still_follow_the_start(client, db_session):
    s = await _setup(client, db_session)
    start = _at(3)
    item = await _interview(client, s["application"]["id"], scheduled_at=start)
    response = await client.patch(f"{INTERVIEWS}/{item['id']}", json={"ends_at": _ends(start, -10)})
    assert response.status_code == 422 and response.json()["detail"][0]["loc"][-1] == "ends_at"


# --- I5 / I6 / AC3 / AC4: notices, invite, time zone --------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_student_notices_carry_the_invite_through_every_change(client, db_session, published, smtp_on):  # noqa: F811
    recruiter, student, application = await _student_setup(client, db_session)
    start = _at(3)
    item = await _interview(client, application.id, scheduled_at=start, ends_at=_ends(start, 30), time_zone="Asia/Dubai", notify=True, meeting_url="https://meet.example.com/a")
    patched = await client.patch(f"{INTERVIEWS}/{item['id']}", json={"meeting_url": "https://meet.example.com/b"})
    assert patched.json()["notifications"] == {"candidate": "in_app", "contact": None}
    await client.post(f"{INTERVIEWS}/{item['id']}/reschedule", json={"scheduled_at": _at(5), "notify": True})
    await client.post(f"{INTERVIEWS}/{item['id']}/cancel", json={"reason": "Position filled", "notify": True})
    rows = await _invites(db_session, student)
    assert [r.context["method"] for r in rows] == ["REQUEST", "REQUEST", "REQUEST", "CANCEL"]
    assert [f"SEQUENCE:{n}" in r.context["ics"] for n, r in enumerate(rows)] == [True] * 4
    assert all(f"UID:interview-{item['id']}@edusphere" in r.context["ics"] for r in rows)
    assert "STATUS:CANCELLED" in rows[-1].context["ics"] and "meet.example.com/b" in rows[1].context["ics"]
    titles = (await db_session.scalars(select(Notification.title).where(Notification.user_id == student.id).order_by(Notification.created_at))).all()
    assert [t for t in titles if t.startswith("Interview")][-4:] == ["Interview scheduled", "Interview updated", "Interview rescheduled", "Interview cancelled"]
    cancelled = await db_session.scalar(select(Notification).where(Notification.user_id == student.id, Notification.title == "Interview cancelled"))
    assert "Position filled" in cancelled.body and "meet.example.com" not in cancelled.body
    await login(client, recruiter)


@pytest.mark.asyncio
async def test_a_non_ist_candidate_reads_the_time_in_their_zone(client, db_session, published, smtp_on):  # noqa: F811
    recruiter, student, application = await _student_setup(client, db_session)
    start = (datetime.now(UTC) + timedelta(days=3)).replace(hour=6, minute=0, second=0, microsecond=0)  # 10:00 in Dubai, 11:30 IST
    iso = start.isoformat().replace("+00:00", "Z")
    await _interview(client, application.id, scheduled_at=iso, ends_at=_ends(iso, 60), time_zone="Asia/Dubai", notify=True)
    note = await db_session.scalar(select(Notification).where(Notification.user_id == student.id, Notification.title == "Interview scheduled"))
    assert "10:00 AM – 11:00 AM Asia/Dubai (UTC+04:00)" in note.body
    rows = await _portal_rows(client, student)
    assert any("10:00 AM – 11:00 AM Asia/Dubai (UTC+04:00)" in r["when"] for r in rows)
    await login(client, recruiter)


@pytest.mark.asyncio
async def test_an_external_candidate_email_carries_the_invite(client, db_session, published, smtp_on):  # noqa: F811
    s = await _setup(client, db_session)
    item = await _interview(client, s["application"]["id"], notify=True, platform="zoom", instructions="Join 5 minutes early")
    message = await db_session.scalar(select(RecruiterMessage).where(RecruiterMessage.id.in_(published)))
    assert "METHOD:REQUEST" in message.calendar_ics and f"interview-{item['id']}" in message.calendar_ics
    assert "Platform: Zoom" in message.body and "Join 5 minutes early" in message.body


@pytest.mark.asyncio
async def test_the_worker_attaches_the_invite(client, db_session, published, smtp_on, monkeypatch):  # noqa: F811
    s = await _setup(client, db_session)
    await _interview(client, s["application"]["id"], notify=True)
    sent: list = []

    def capture(msg):
        sent.append(msg)

    monkeypatch.setattr(mailer, "_send_sync", capture)
    assert await recruiter_email.deliver_recruiter_email(published[0]) == "sent"
    parts = [p for p in message_from_bytes(sent[0].as_bytes()).walk() if p.get_content_type() == "text/calendar"]
    assert len(parts) == 1 and parts[0].get_param("method") == "REQUEST" and parts[0].get_filename() == "invite.ics"


def test_a_lead_email_without_an_invite_has_no_attachment():
    msg = mailer.lead_email_message(to_email="a@example.com", subject="Hi", body="Body", sender_name="R", sender_email="r@example.com")
    assert not [p for p in msg.walk() if p.get_content_type() == "text/calendar"]


# --- I7: the student portal ---------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_portal_shows_a_cancelled_interview_with_its_reason_and_no_link(client, db_session):
    recruiter, student, application = await _student_setup(client, db_session)
    item = await _interview(client, application.id, meeting_url="https://meet.example.com/gone", round_number=2, platform="microsoft_teams", instructions="Formal dress")
    await client.post(f"{INTERVIEWS}/{item['id']}/cancel", json={"reason": "Candidate requested", "notify": False})
    rows = await _portal_rows(client, student)
    row = next(r for r in rows if r["status"].startswith("Cancelled"))
    assert row["status"] == "Cancelled — Candidate requested" and row["link"] is None and "gone" not in str(rows)
    assert row["round"] == "HR Round (round 2)" and "Microsoft Teams" in row["details"] and "Formal dress" in row["details"]
    await login(client, recruiter)


@pytest.mark.asyncio
async def test_details_event_rows_never_reach_the_portal(client, db_session):
    _recruiter, _student, application = await _student_setup(client, db_session)
    item = await _interview(client, application.id, meeting_url="https://meet.example.com/one")
    await client.patch(f"{INTERVIEWS}/{item['id']}", json={"meeting_url": "https://meet.example.com/two", "notify": False})
    event = await db_session.scalar(select(InterviewEvent).where(InterviewEvent.interview_id == item["id"], InterviewEvent.event == "details"))
    assert event.old_meeting_url == "https://meet.example.com/one"


def test_labels_cover_the_new_status_and_platforms():
    assert svc.STATUS_LABELS["cancelled"] == "Cancelled" and svc.CANCELLABLE == ("scheduled", "confirmed", "rescheduled", "on_hold")
    assert svc.PLATFORM_LABELS == {"google_meet": "Google Meet", "microsoft_teams": "Microsoft Teams", "zoom": "Zoom", "zoho_meeting": "Zoho Meeting", "other": "Other"}
