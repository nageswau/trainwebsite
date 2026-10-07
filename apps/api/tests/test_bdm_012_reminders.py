"""bdm-012 (DEC-SCOPE-098) AC1-AC4 + R4-R8, R11, R12 -- the reminder job: each kind fires once at its IST time, to the owner at fire
time, never for a closed record, never twice; a new time is a new reminder; one failure never stops the run."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import update

from app.core.database import SessionLocal
from app.models import BdmAppointment, BdmMou, User
from app.services import bdm_reminders
from tests.bdm002_helpers import make_bdm
from tests.bdm012_helpers import NINE, D, appointment, deliveries, ist, mou, reminders, run, task, trip, world
from tests.bdm025_helpers import org

TOMORROW_TEN = ist(D + timedelta(days=1), 10)


@pytest_asyncio.fixture
async def w(db_session):
    return await world(db_session)


def _titles(items) -> list[str]:
    return sorted(n.title for n in items)


# --- the beat entry ---------------------------------------------------------------------------------------------------------------


def test_beat_runs_the_reminder_job_every_five_minutes_beside_the_existing_entries():
    from app.worker import celery

    entry = celery.conf.beat_schedule["bdm012-reminders"]
    assert entry == {"task": "app.worker.send_bdm_reminders_task", "schedule": 300.0}
    assert "app.worker.send_bdm_reminders_task" in celery.tasks
    assert {"enh014-sweep-stale-deliveries", "agn017-daily-reminders"} <= set(celery.conf.beat_schedule)


# --- appointments (§6) --------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_day_before_fires_at_0900_ist_with_the_source_content_and_no_contact_details(db_session, w):
    bdm, organization = w
    appt = await appointment(db_session, bdm, organization, TOMORROW_TEN)
    await run(db_session, NINE - timedelta(minutes=1))
    assert await reminders(db_session, bdm) == []

    await run(db_session, NINE)
    (note,) = await reminders(db_session, bdm)
    assert note.title == "Appointment reminder"
    assert note.body == (f"Tomorrow at 10:00 AM. Organization: {organization.name}. Contact: Mr. XYZ. Purpose: Edusphere Course Promotion. Location: Vijayawada. Please confirm your appointment.")
    assert "9876543210" not in note.body and "xyz@abc.example" not in note.body
    assert note.action_url == f"/bdm/appointments/{appt.id}"
    (email,) = await deliveries(db_session, note)
    assert email.channel == "email" and email.context == {
        "kind": "bdm_reminder",
        "links": [
            {"label": "Confirmed", "path": f"/bdm/appointments/{appt.id}?action=confirm"},
            {"label": "Reschedule", "path": f"/bdm/appointments/{appt.id}?action=reschedule"},
            {"label": "Cancel", "path": f"/bdm/appointments/{appt.id}?action=cancel"},
        ],
    }


@pytest.mark.asyncio
async def test_a_confirmed_appointment_is_not_asked_to_confirm_again(db_session, w):
    bdm, organization = w
    appt = await appointment(db_session, bdm, organization, TOMORROW_TEN, status="confirmed")
    await run(db_session, NINE)
    (note,) = await reminders(db_session, bdm)
    assert "Please confirm" not in note.body
    (email,) = await deliveries(db_session, note)
    assert [link["label"] for link in email.context["links"]] == ["Reschedule", "Cancel"]
    assert appt.id


@pytest.mark.asyncio
async def test_the_day_before_reminder_catches_up_later_the_same_day_only(db_session, w):
    bdm, organization = w
    await appointment(db_session, bdm, organization, TOMORROW_TEN)
    await run(db_session, ist(D + timedelta(days=1), 0, 5))  # the next IST day: the day-before window has closed (R4)
    assert await reminders(db_session, bdm) == []
    await run(db_session, ist(D, 23, 55))
    assert _titles(await reminders(db_session, bdm)) == ["Appointment reminder"]


@pytest.mark.asyncio
async def test_hour_before_fires_exactly_one_hour_before_with_organization_time_and_location(db_session, w):
    bdm, organization = w
    starts = ist(D, 15, 30)
    appt = await appointment(db_session, bdm, organization, starts, location=None)
    await run(db_session, starts - timedelta(hours=1, seconds=1))
    assert [n.title for n in await reminders(db_session, bdm)] == []
    await run(db_session, starts - timedelta(hours=1))
    (note,) = await reminders(db_session, bdm)
    assert (note.title, note.body) == ("Appointment in 1 hour", f"Your appointment with {organization.name} is at 03:30 PM.")
    assert note.action_url == f"/bdm/appointments/{appt.id}"
    await run(db_session, starts)  # it has started: nothing more
    assert len(await reminders(db_session, bdm)) == 1


@pytest.mark.asyncio
async def test_an_appointment_booked_less_than_an_hour_ahead_gets_only_the_hour_reminder(db_session, w):
    bdm, organization = w
    now = ist(D, 14, 20)
    await appointment(db_session, bdm, organization, now + timedelta(minutes=40))
    await run(db_session, now)
    assert _titles(await reminders(db_session, bdm)) == ["Appointment in 1 hour"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["cancelled", "completed", "no_show"])
async def test_closed_appointments_never_fire(db_session, w, status):
    bdm, organization = w
    await appointment(db_session, bdm, organization, TOMORROW_TEN, status=status)
    await appointment(db_session, bdm, organization, ist(D, 9, 30), status=status)
    await run(db_session, NINE)
    assert await reminders(db_session, bdm) == []


@pytest.mark.asyncio
async def test_a_rescheduled_appointment_fires_relative_to_its_new_time(db_session, w):
    bdm, organization = w
    appt = await appointment(db_session, bdm, organization, TOMORROW_TEN)
    await run(db_session, NINE)
    new_start = ist(D + timedelta(days=2), 11)
    await db_session.execute(update(BdmAppointment).where(BdmAppointment.id == appt.id).values(starts_at=new_start, status="rescheduled"))
    await db_session.commit()
    await run(db_session, NINE + timedelta(minutes=5))  # nothing new today: the new time is the day after tomorrow
    assert len(await reminders(db_session, bdm)) == 1
    await run(db_session, ist(D + timedelta(days=1), 9))
    latest = (await reminders(db_session, bdm))[-1]
    assert len(await reminders(db_session, bdm)) == 2 and latest.body.startswith("Tomorrow at 11:00 AM.")


@pytest.mark.asyncio
async def test_a_reassigned_appointment_reminds_the_new_owner_only(db_session, w):
    bdm, organization = w
    other = await make_bdm(db_session, await _manager_of(db_session, bdm))
    appt = await appointment(db_session, bdm, organization, TOMORROW_TEN)
    await db_session.execute(update(BdmAppointment).where(BdmAppointment.id == appt.id).values(bdm_user_id=other.id))
    await db_session.commit()
    await run(db_session, NINE)
    assert await reminders(db_session, bdm) == [] and _titles(await reminders(db_session, other)) == ["Appointment reminder"]


async def _manager_of(db, bdm: User) -> User:
    from sqlalchemy import select

    from app.models import BdmProfile

    manager_id = await db.scalar(select(BdmProfile.reporting_manager_user_id).where(BdmProfile.user_id == bdm.id))
    return await db.get(User, manager_id)


@pytest.mark.asyncio
async def test_an_inactive_owner_gets_nothing(db_session, w):
    bdm, organization = w
    await appointment(db_session, bdm, organization, TOMORROW_TEN)
    await db_session.execute(update(User).where(User.id == bdm.id).values(active=False))
    await db_session.commit()
    await run(db_session, NINE)
    assert await reminders(db_session, bdm) == []


# --- AC4: exactly once ----------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rerunning_the_job_sends_no_duplicates(db_session, w, enqueued):
    bdm, organization = w
    await appointment(db_session, bdm, organization, TOMORROW_TEN)
    await run(db_session, NINE)
    published = len(enqueued)
    counts = await run(db_session, NINE + timedelta(minutes=5))
    assert len(await reminders(db_session, bdm)) == 1 and len(enqueued) == published
    assert counts["duplicate"] >= 1


@pytest.mark.asyncio
async def test_two_overlapping_runs_create_one_reminder(db_session, w):
    bdm, organization = w
    await appointment(db_session, bdm, organization, TOMORROW_TEN)

    async def one():
        async with SessionLocal() as db:
            return await run(db, NINE)

    await asyncio.gather(one(), one())
    assert len(await reminders(db_session, bdm)) == 1


@pytest.mark.asyncio
async def test_one_failing_reminder_is_counted_and_the_run_goes_on(db_session, w, monkeypatch):
    bdm, organization = w
    first = await appointment(db_session, bdm, organization, TOMORROW_TEN)
    await appointment(db_session, bdm, organization, TOMORROW_TEN + timedelta(hours=3))
    real = bdm_reminders.queue_deliveries

    async def flaky(db, note, user, **kw):
        if str(first.id) in note.action_url:
            raise RuntimeError("boom")
        return await real(db, note, user, **kw)

    monkeypatch.setattr(bdm_reminders, "queue_deliveries", flaky)
    counts = await run(db_session, NINE)
    assert counts["failed"] == 1
    (note,) = await reminders(db_session, bdm)
    assert str(first.id) not in note.action_url


# --- travel (§7) ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_travel_fires_the_day_before_with_destination_purpose_and_linked_appointments(db_session, w):
    bdm, organization = w
    t = await trip(db_session, bdm, D + timedelta(days=1))
    for hour, status in ((10, "scheduled"), (12, "confirmed"), (15, "cancelled")):
        await appointment(db_session, bdm, organization, ist(D + timedelta(days=1), hour), status=status, trip_id=t.id)
    await run(db_session, NINE)
    note = next(n for n in await reminders(db_session, bdm) if n.title == "Travel reminder")
    assert note.body == f"Tomorrow (11 May 2033): travel to Vijayawada. BDM: {bdm.full_name}. Purpose: College visits. Appointments: 2."
    assert note.action_url == f"/bdm/travel/{t.id}"
    (email,) = await deliveries(db_session, note)
    assert email.context["links"] == [
        {"label": "View Appointments", "path": f"/bdm/travel/{t.id}#trip-appointments"},
        {"label": "View Expenses", "path": f"/bdm/travel/{t.id}#trip-costs"},
        {"label": "Add Remarks", "path": f"/bdm/travel/{t.id}#trip-remarks"},
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(("approval", "travel"), [("draft", "planned"), ("submitted", "planned"), ("rejected", "planned"), ("approved", "cancelled")])
async def test_unapproved_or_cancelled_trips_never_fire(db_session, w, approval, travel):
    bdm, _ = w
    await trip(db_session, bdm, D + timedelta(days=1), approval=approval, travel=travel)
    await run(db_session, NINE)
    assert await reminders(db_session, bdm) == []


# --- follow-ups and tasks (§4 Common) ---------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_follow_ups_and_tasks_fire_at_0900_on_the_due_day(db_session, w):
    bdm, organization = w
    await task(db_session, bdm, D, organization=organization)
    await task(db_session, bdm, D, kind="task", title="Send\r\nbrochure")
    await task(db_session, bdm, D + timedelta(days=1))
    await run(db_session, NINE - timedelta(minutes=1))
    assert await reminders(db_session, bdm) == []
    await run(db_session, NINE)
    notes = {n.title: n for n in await reminders(db_session, bdm)}
    assert set(notes) == {"Follow-up due today", "Task due today"}
    assert notes["Follow-up due today"].body == f"Call the principal. Organization: {organization.name}. Due 10 May 2033."
    assert notes["Task due today"].body == "Send brochure. Due 10 May 2033."
    assert notes["Task due today"].action_url == "/bdm/follow-ups?kind=task"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["done", "cancelled"])
async def test_closed_tasks_never_fire(db_session, w, status):
    bdm, _ = w
    await task(db_session, bdm, D, status=status)
    await run(db_session, NINE)
    assert await reminders(db_session, bdm) == []


# --- MoU (§10, D19) ---------------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(("days", "fires"), [(4, False), (5, True), (7, False), (10, True), (15, True)])
async def test_a_proposal_reminds_every_five_days_while_it_stays_sent(db_session, w, days, fires):
    bdm, organization = w
    m = await mou(db_session, organization, status="proposal_sent", changed=ist(D - timedelta(days=days), 17))
    await run(db_session, NINE)
    notes = await reminders(db_session, bdm)
    if not fires:
        assert notes == []
        return
    (note,) = notes
    assert (note.title, note.body) == ("MoU follow-up", f"{organization.name}: the proposal was sent {days} days ago. Follow up with the contact person.")
    assert note.action_url == f"/bdm/organizations/{organization.id}#org-mou" and m.id


@pytest.mark.asyncio
async def test_a_shared_draft_reminds_and_other_statuses_or_old_rows_do_not(db_session, w):
    bdm, organization = w
    await mou(db_session, organization, status="draft_shared", changed=ist(D - timedelta(days=5), 10))
    other = await org(db_session, bdm)
    await mou(db_session, other, status="under_negotiation", changed=ist(D - timedelta(days=5), 10))
    stale = await org(db_session, bdm)
    await mou(db_session, stale, status="proposal_sent", changed=ist(D - timedelta(days=5), 10), current=False)
    archived = await org(db_session, bdm, archived=True)
    await mou(db_session, archived, status="proposal_sent", changed=ist(D - timedelta(days=5), 10))
    await run(db_session, NINE)
    (note,) = await reminders(db_session, bdm)
    assert note.body == f"{organization.name}: the draft was shared 5 days ago. Follow up with the contact person."


@pytest.mark.asyncio
async def test_an_active_mou_reminds_thirty_days_before_valid_until(db_session, w):
    bdm, organization = w
    await mou(db_session, organization, status="active", changed=ist(D - timedelta(days=200), 10), valid_until=D + timedelta(days=30))
    later = await org(db_session, bdm)
    await mou(db_session, later, status="active", changed=ist(D - timedelta(days=200), 10), valid_until=D + timedelta(days=31))
    await run(db_session, NINE)
    (note,) = await reminders(db_session, bdm)
    assert (note.title, note.body) == ("MoU renewal due", f"{organization.name}: the MoU is valid until 09 Jun 2033. Plan the renewal with the contact person.")


@pytest.mark.asyncio
async def test_a_reassigned_organization_sends_its_mou_reminder_to_the_new_owner(db_session, w):
    from app.models import BdmOrganization

    bdm, organization = w
    other = await make_bdm(db_session, await _manager_of(db_session, bdm))
    await mou(db_session, organization, status="proposal_sent", changed=ist(D - timedelta(days=5), 10))
    await db_session.execute(update(BdmOrganization).where(BdmOrganization.id == organization.id).values(assigned_bdm_user_id=other.id))
    await db_session.commit()
    await run(db_session, NINE)
    assert await reminders(db_session, bdm) == [] and _titles(await reminders(db_session, other)) == ["MoU follow-up"]


@pytest.mark.asyncio
async def test_a_status_change_restarts_the_mou_clock(db_session, w):
    bdm, organization = w
    m = await mou(db_session, organization, status="proposal_sent", changed=ist(D - timedelta(days=5), 10))
    await run(db_session, NINE)
    await db_session.execute(update(BdmMou).where(BdmMou.id == m.id).values(status="draft_shared", status_changed_at=ist(D, 8)))
    await db_session.commit()
    await run(db_session, ist(D + timedelta(days=5), 9))
    assert [n.body.split(": ", 1)[1] for n in await reminders(db_session, bdm)] == [
        "the proposal was sent 5 days ago. Follow up with the contact person.",
        "the draft was shared 5 days ago. Follow up with the contact person.",
    ]


@pytest.mark.asyncio
async def test_the_run_logs_counts_only(db_session, w, caplog):
    import logging

    bdm, organization = w
    await appointment(db_session, bdm, organization, TOMORROW_TEN)
    with caplog.at_level(logging.INFO, logger="app.services.bdm_reminders"):
        counts = await run(db_session, NINE)
    assert counts["created"] >= 1
    text = " ".join(r.getMessage() + str(getattr(r, "extra_fields", "")) for r in caplog.records)
    assert "bdm012_reminders_done" in text and organization.name not in text and "Mr. XYZ" not in text


def test_the_worker_entry_point_runs_with_its_own_session_and_the_current_time(monkeypatch):
    seen = {}

    async def fake(db, *, now):
        seen["now"] = now
        return {"created": 0}

    monkeypatch.setattr(bdm_reminders, "send_bdm_reminders", fake)
    assert asyncio.run(bdm_reminders.run_bdm_reminders()) == {"created": 0}
    assert abs(seen["now"] - datetime.now(UTC)) < timedelta(minutes=1)
