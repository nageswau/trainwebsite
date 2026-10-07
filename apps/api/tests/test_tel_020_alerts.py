"""tel-020 (DEC-SCOPE-110; EVID-019 §20, T14) AC1-AC4 -- the nine telecaller alerts. Event alerts ride the write's transaction; the six
time-based ones come from the 15-minute beat, each once per (kind, object, user, event time). Beat rows are dated 2033, so other tests'
rows (the database is shared and never truncated) stay out of the windows; every assertion is about this test's own telecaller."""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy import select, update

from app.models import Appointment, Enquiry, LeadCall, LeadFollowUp, Notification, NotificationDelivery, TelSetting, User
from app.services import lead_distribution, telecaller_alerts
from tests.tel004_helpers import make_telecaller, make_tl_manager
from tests.tel016_helpers import action_url, as_user, book, make_counselor, setup
from tests.tel018_helpers import c_url, handover
from tests.test_tel_020_settings import reset_settings

IST = ZoneInfo("Asia/Kolkata")
D = date(2033, 5, 10)


def ist(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), IST).astimezone(UTC)


@pytest_asyncio.fixture
async def tel(db_session):
    await reset_settings(db_session)
    return await make_telecaller(db_session, await make_tl_manager(db_session))


async def mk_lead(db, owner: User, **over) -> Enquiry:
    fields = {"division": "it", "name": f"Asha {uuid.uuid4().hex[:5]}", "email": f"{uuid.uuid4().hex[:8]}@example.local", "phone": "9876543210",
              "subject": "Python", "message": "", "source": "website", "status": "contacted", "telecaller_user_id": owner.id,
              "stage_changed_at": ist(D, 9), "created_at": ist(D, 9)}
    row = Enquiry(**(fields | over))
    db.add(row)
    await db.commit()
    return row


async def follow_up(db, lead: Enquiry, due_at: datetime, *, status: str = "open") -> LeadFollowUp:
    row = LeadFollowUp(lead_id=lead.id, due_at=due_at, reason="fee_details", created_by_user_id=lead.telecaller_user_id, status=status,
                       completed_at=due_at if status == "done" else None, completed_by_user_id=lead.telecaller_user_id if status == "done" else None)
    db.add(row)
    await db.commit()
    return row


async def appointment(db, lead: Enquiry, at: datetime, *, status: str = "scheduled") -> Appointment:
    counselor = await make_counselor(db, lead.division)
    row = Appointment(division=lead.division, lead_id=lead.id, staff_id=counselor.id, scheduled_at=at, appointment_type="it_course_counselling",
                      mode="Online", status=status, appointment_code=f"CAP-T{uuid.uuid4().hex[:8]}", booked_by_user_id=lead.telecaller_user_id)
    db.add(row)
    await db.commit()
    return row


async def run(db, now: datetime) -> dict:
    return await telecaller_alerts.send_telecaller_alerts(db, now=now)


async def notes(db, user: User, title: str | None = None) -> list[Notification]:
    query = select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at)
    if title:
        query = query.where(Notification.title == title)
    return list(await db.scalars(query.execution_options(populate_existing=True)))


async def deliveries(db, note: Notification) -> list[NotificationDelivery]:
    return list(await db.scalars(select(NotificationDelivery).where(NotificationDelivery.notification_id == note.id)))


# --- the beat entry ---------------------------------------------------------------------------------------------------------------


def test_beat_runs_the_alert_job_every_fifteen_minutes_beside_the_existing_entries():
    from app.worker import celery

    assert celery.conf.beat_schedule["tel020-alerts"] == {"task": "app.worker.send_telecaller_alerts_task", "schedule": 900.0}
    assert "app.worker.send_telecaller_alerts_task" in celery.tasks
    assert {"bdm012-reminders", "tel018-conversion-sweep", "agn017-daily-reminders"} <= set(celery.conf.beat_schedule)


# --- follow-ups (AL4, AL10) -------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_follow_up_due_fires_once_in_the_quarter_hour_before_with_an_email_and_no_contact_details(db_session, tel):
    """Backlog positive scenario: a follow-up at 16:00 -> "Follow-up due" at the 15:45-16:00 run (AC1)."""
    lead = await mk_lead(db_session, tel)
    await follow_up(db_session, lead, ist(D, 16))
    await run(db_session, ist(D, 15, 44))
    assert await notes(db_session, tel) == []
    await run(db_session, ist(D, 15, 45))
    await run(db_session, ist(D, 15, 59))
    (note,) = await notes(db_session, tel)
    assert note.title == "Follow-up due" and note.action_url == "/telecaller/follow-ups"
    assert note.body == f"Your follow-up with {lead.name} ({lead.lead_code}) is due at 04:00 PM IST on 10 May 2033."
    assert "9876543210" not in note.body and lead.email not in note.body
    (email,) = await deliveries(db_session, note)
    assert (email.channel, email.context) == ("email", {"kind": "tel_alert", "links": [{"label": "Open follow-ups", "path": "/telecaller/follow-ups"}]})


@pytest.mark.asyncio
async def test_a_late_run_still_sends_due_then_missed_follows_one_hour_after_and_never_twice(db_session, tel):
    """AC2: a run 30 minutes late catches up; Missed fires when still open 1 h after the due time (AL4)."""
    lead = await mk_lead(db_session, tel)
    await follow_up(db_session, lead, ist(D, 16))
    await run(db_session, ist(D, 16, 30))
    assert [n.title for n in await notes(db_session, tel)] == ["Follow-up due"]
    await run(db_session, ist(D, 16, 59))
    assert [n.title for n in await notes(db_session, tel)] == ["Follow-up due"]
    for minute in (0, 15):
        await run(db_session, ist(D, 17, minute))
    missed = await notes(db_session, tel, "Missed follow-up")
    assert len(missed) == 1 and missed[0].body == f"Your follow-up with {lead.name} ({lead.lead_code}) due at 04:00 PM IST on 10 May 2033 is still open."


@pytest.mark.asyncio
async def test_a_follow_up_older_than_a_day_a_completed_one_and_a_closed_lead_alert_nothing(db_session, tel):
    lead = await mk_lead(db_session, tel)
    await follow_up(db_session, lead, ist(D, 16) - timedelta(hours=26))
    await follow_up(db_session, lead, ist(D, 16), status="done")
    await run(db_session, ist(D, 15, 50))
    await run(db_session, ist(D, 17, 5))
    assert await notes(db_session, tel) == []


@pytest.mark.asyncio
async def test_a_rescheduled_follow_up_re_arms(db_session, tel):
    """Backlog edge case: the due time is part of the key, so a new time is a new alert."""
    lead = await mk_lead(db_session, tel)
    fu = await follow_up(db_session, lead, ist(D, 16))
    await run(db_session, ist(D, 15, 50))
    await db_session.execute(update(LeadFollowUp).where(LeadFollowUp.id == fu.id).values(due_at=ist(D, 18)))
    await db_session.commit()
    await run(db_session, ist(D, 17, 50))
    assert len(await notes(db_session, tel, "Follow-up due")) == 2


# --- appointments (AL4, AL10) -----------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_appointment_in_one_hour_fires_once(db_session, tel):
    lead = await mk_lead(db_session, tel)
    await appointment(db_session, lead, ist(D, 11))
    await run(db_session, ist(D, 9, 59))
    assert await notes(db_session, tel) == []
    await run(db_session, ist(D, 10))
    await run(db_session, ist(D, 10, 30))
    (note,) = await notes(db_session, tel)
    assert (note.title, note.action_url) == ("Appointment in 1 hour", f"/telecaller/leads/{lead.id}")
    assert note.body == f"The counselling appointment for {lead.name} ({lead.lead_code}) starts at 11:00 AM IST on 10 May 2033."


@pytest.mark.asyncio
async def test_appointment_tomorrow_fires_once_from_six_pm_ist_the_day_before_and_never_for_a_cancelled_one(db_session, tel):
    lead = await mk_lead(db_session, tel)
    await appointment(db_session, lead, ist(D + timedelta(days=1), 10))
    other = await mk_lead(db_session, tel)
    await appointment(db_session, other, ist(D + timedelta(days=1), 12), status="cancelled")
    await run(db_session, ist(D, 17, 59))
    assert await notes(db_session, tel) == []
    for hour in (18, 23):
        await run(db_session, ist(D, hour))
    (note,) = await notes(db_session, tel)
    assert note.title == "Appointment tomorrow"
    assert note.body == f"{lead.name} ({lead.lead_code}) has a counselling appointment tomorrow at 10:00 AM IST on 11 May 2033."


# --- thresholds (AL1, AL8, AL9; AC4) ----------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lead_not_contacted_uses_the_team_threshold_from_the_next_run(db_session, tel):
    lead = await mk_lead(db_session, tel, status="assigned", stage_changed_at=ist(D, 9))
    await mk_lead(db_session, tel, status="contacted", stage_changed_at=ist(D, 9) - timedelta(days=3))  # contacted: never alerted
    await run(db_session, ist(D, 12))
    assert await notes(db_session, tel) == []
    await db_session.execute(update(TelSetting).where(TelSetting.team == "it").values(not_contacted_hours=2))
    await db_session.commit()
    await run(db_session, ist(D, 12))
    await run(db_session, ist(D, 12, 15))
    (note,) = await notes(db_session, tel)
    assert (note.title, note.action_url) == ("Lead not contacted", f"/telecaller/leads/{lead.id}")
    assert note.body == f"{lead.name} ({lead.lead_code}) has not been contacted for over 2 hours."
    await reset_settings(db_session)


@pytest.mark.asyncio
async def test_lead_not_contacted_at_the_default_24_hours_and_never_for_a_handed_over_lead(db_session, tel):
    lead = await mk_lead(db_session, tel, status="first_call_pending", stage_changed_at=ist(D, 9))
    counselor = await make_counselor(db_session)
    await mk_lead(db_session, tel, status="first_call_pending", stage_changed_at=ist(D, 9), owner_id=counselor.id)
    await run(db_session, ist(D + timedelta(days=1), 8, 59))
    assert await notes(db_session, tel) == []
    await run(db_session, ist(D + timedelta(days=1), 9))
    assert [n.action_url for n in await notes(db_session, tel)] == [f"/telecaller/leads/{lead.id}"]


@pytest.mark.asyncio
async def test_hot_lead_pending_after_4_hours_without_a_call_and_a_new_call_re_arms(db_session, tel):
    lead = await mk_lead(db_session, tel, priority="hot", created_at=ist(D, 9))
    await mk_lead(db_session, tel, priority="warm", created_at=ist(D, 9))
    await mk_lead(db_session, tel, priority="hot", created_at=ist(D, 9), status="not_interested")  # closed
    await run(db_session, ist(D, 12, 59))
    assert await notes(db_session, tel) == []
    await run(db_session, ist(D, 13))
    (note,) = await notes(db_session, tel)
    assert note.title == "Hot lead pending" and note.body == f"Hot lead {lead.name} ({lead.lead_code}) has had no call for over 4 hours."
    db_session.add(LeadCall(lead_id=lead.id, caller_user_id=tel.id, occurred_at=ist(D, 14), duration_seconds=60, call_type="outgoing", outcome="busy"))
    await db_session.commit()
    await run(db_session, ist(D, 15))
    assert len(await notes(db_session, tel)) == 1
    await run(db_session, ist(D, 18))
    assert len(await notes(db_session, tel, "Hot lead pending")) == 2


@pytest.mark.asyncio
async def test_an_inactive_telecaller_gets_no_alerts(db_session, tel):
    """Backlog negative scenario."""
    lead = await mk_lead(db_session, tel, priority="hot", status="assigned")
    await follow_up(db_session, lead, ist(D, 16))
    await appointment(db_session, lead, ist(D, 16, 30))
    await db_session.execute(update(User).where(User.id == tel.id).values(active=False))
    await db_session.commit()
    for at in (ist(D, 15, 50), ist(D, 17, 30), ist(D + timedelta(days=2), 9)):
        await run(db_session, at)
    assert await notes(db_session, tel) == []


@pytest.mark.asyncio
async def test_the_dashboard_overdue_tile_uses_the_team_threshold(db_session, tel):
    """AL12 (tel-021 DB1): the not-contacted part of B9 Overdue follows the team's hours instead of a fixed 24."""
    from app.services import telecaller_metrics

    now = datetime.now(UTC)
    await mk_lead(db_session, tel, status="first_call_pending", stage_changed_at=now - timedelta(hours=3), created_at=now - timedelta(hours=3))
    assert (await telecaller_metrics.tiles(db_session, tel.id, "it", now))["overdue"] == 0
    await db_session.execute(update(TelSetting).where(TelSetting.team == "it").values(not_contacted_hours=2))
    await db_session.commit()
    assert (await telecaller_metrics.tiles(db_session, tel.id, "it", now))["overdue"] == 1
    await reset_settings(db_session)


# --- event alerts (AL5, AL7; AC3)-------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_manual_assignment_alerts_the_new_telecaller_once(client, db_session):
    manager = await make_tl_manager(db_session)
    first, second = await make_telecaller(db_session, manager), await make_telecaller(db_session, manager)
    lead = await mk_lead(db_session, first, status="assigned")
    await as_user(client, manager)
    payload = {"lead_ids": [str(lead.id)], "telecaller_user_id": str(second.id)}
    assert (await client.post("/api/v1/telecaller/leads/assign", json=payload)).status_code == 200
    assert (await client.post("/api/v1/telecaller/leads/assign", json=payload)).json()["unchanged"] == 1  # same telecaller: no new alert
    (note,) = await notes(db_session, second)
    assert (note.title, note.action_url, note.dedupe_key) == ("New lead assigned", f"/telecaller/leads/{lead.id}", None)
    assert note.body == f"{lead.name} ({lead.lead_code}) is now assigned to you." and "9876543210" not in note.body
    (email,) = await deliveries(db_session, note)
    assert email.context == {"kind": "tel_alert", "links": [{"label": "Open lead", "path": f"/telecaller/leads/{lead.id}"}]}
    assert await notes(db_session, first) == []


@pytest.mark.asyncio
async def test_a_rolled_back_assignment_sends_nothing_and_an_inactive_or_acting_telecaller_gets_nothing(db_session, tel):
    """AC3 (outbox): the notice is in the write's transaction."""
    lead = await mk_lead(db_session, tel, telecaller_user_id=None, status="new")
    lead_id, tel_id = lead.id, tel.id
    await lead_distribution.assign(db_session, lead, tel_id, "manual", None)
    await db_session.rollback()
    tel = await db_session.get(User, tel_id)  # the rollback expired both rows
    assert await notes(db_session, tel) == []
    lead = await db_session.get(Enquiry, lead_id)
    await lead_distribution.assign(db_session, lead, tel_id, "manual", tel)  # the actor is the recipient
    await db_session.commit()
    assert await notes(db_session, tel) == []
    inactive = await make_telecaller(db_session, await make_tl_manager(db_session))
    inactive.active = False
    await db_session.commit()
    await lead_distribution.assign(db_session, await db_session.get(Enquiry, lead_id), inactive.id, "manual", None)
    await db_session.commit()
    assert await notes(db_session, inactive) == []


@pytest.mark.asyncio
async def test_a_lifecycle_move_sends_no_per_lead_alert(db_session, tel):
    """AL13: tel-025's deactivation / team move tells the new telecaller once (its D6 summary), never once per moved lead."""
    from app.services import telecaller_lifecycle

    other = await make_telecaller(db_session, await make_tl_manager(db_session))
    leads = [await mk_lead(db_session, other, status="contacted") for _ in range(2)]
    await telecaller_lifecycle.move_leads(db_session, other, leads, tel, "deactivation")
    await db_session.commit()
    assert await notes(db_session, tel, "New lead assigned") == []


@pytest.mark.asyncio
async def test_the_counselor_completing_an_appointment_alerts_the_telecaller(client, db_session):
    _, tel, counselor, lead = await setup(db_session)
    out = (await book(client, tel, lead, counselor)).json()
    await db_session.execute(update(Appointment).where(Appointment.id == uuid.UUID(out["id"])).values(scheduled_at=datetime.now(UTC) - timedelta(hours=2)))
    await db_session.commit()
    await as_user(client, counselor)
    assert (await client.post(action_url(out["id"], "complete"))).status_code == 200
    (note,) = await notes(db_session, tel)
    assert (note.title, note.action_url) == ("Counselor appointment completed", f"/telecaller/leads/{lead.id}")
    assert note.body.startswith(f"The counselling appointment for {lead.name} ({lead.lead_code}) on ") and note.body.endswith(" was completed.")
    assert counselor.full_name not in note.body and "9876543210" not in note.body


@pytest.mark.asyncio
async def test_a_returned_lead_alerts_the_telecaller_without_the_reason(client, db_session):
    _, tel, counselor, lead = await setup(db_session, status="counselling_completed")
    assert (await handover(client, tel, lead, counselor)).status_code == 200
    await as_user(client, counselor)
    assert (await client.post(c_url(lead.id, "/return"), json={"reason": "Wants a fee discount"})).status_code == 200
    (note,) = await notes(db_session, tel)
    assert (note.title, note.action_url) == ("Lead returned for follow-up", f"/telecaller/leads/{lead.id}")
    assert note.body == f"{lead.name} ({lead.lead_code}) was returned to you for follow-up." and "discount" not in note.body
