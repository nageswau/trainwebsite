"""tel-021 (DEC-SCOPE-103, spec §2): every Appendix B count on fixture data -- the daily activity D1-D13, the dashboard tiles B1-B10 and
target progress. The shared test database is never truncated, so each test counts only for users it created."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from app.models import (
    BDM_APPOINTMENT_ALL_TYPES,
    Appointment,
    AuditLog,
    BdmAppointment,
    BdmMeetingRequest,
    Enquiry,
    LeadCall,
    LeadFollowUp,
    LeadMessage,
    LeadStageHistory,
    TelTarget,
)
from app.services import telecaller_metrics as metrics
from app.services.bdm_activities import day_range
from app.services.bdm_appointments import db_now, today_ist
from tests.bdm002_helpers import create_org, make_bdm
from tests.bdm017_helpers import as_user
from tests.bdm001_helpers import make_manager
from tests.tel004_helpers import make_telecaller, make_tl_manager

pytestmark = pytest.mark.asyncio


async def team(db):
    manager = await make_tl_manager(db)
    return manager, await make_telecaller(db, manager), await make_telecaller(db, manager)


async def clock(db) -> tuple[datetime, date, datetime, datetime]:
    now = await db_now(db)
    today = today_ist(now)
    start, end = day_range(today)
    return now, today, start, end


async def add(db, *rows):
    db.add_all(rows)
    await db.commit()
    return rows[0] if len(rows) == 1 else rows


async def make_lead(db, tel=None, **over) -> Enquiry:
    values = {"division": "it", "name": f"Lead {uuid.uuid4().hex[:6]}", "email": f"{uuid.uuid4().hex[:8]}@example.local", "subject": "Python",
              "message": "Hi", "source": "website", "status": "assigned", "telecaller_user_id": tel.id if tel else None} | over
    return await add(db, Enquiry(**values))


def call(lead, tel, at, outcome="interested") -> LeadCall:
    return LeadCall(lead_id=lead.id, caller_user_id=tel.id, occurred_at=at, duration_seconds=60, call_type="outgoing", outcome=outcome)


def follow_up(lead, tel, due, **over) -> LeadFollowUp:
    return LeadFollowUp(**({"lead_id": lead.id, "due_at": due, "reason": "fee_details", "created_by_user_id": tel.id} | over))


def history(lead, to_stage, actor, at, from_stage="contacted", event="manual") -> LeadStageHistory:
    return LeadStageHistory(lead_id=lead.id, from_stage=from_stage, to_stage=to_stage, event=event, actor_user_id=actor.id if actor else None, created_at=at)


def audit(action, lead, at, actor=None, **meta) -> AuditLog:
    return AuditLog(user_id=actor.id if actor else None, action=action, entity_type="enquiry", entity_id=str(lead.id), metadata_json=meta, created_at=at)


def assign(lead, at, before, after) -> AuditLog:
    return audit("lead.assign", lead, at, **{"from": str(before.id) if before else None, "to": str(after.id), "method": "manual"})


def lead_appt(lead, tel, scheduled, created, status="scheduled") -> Appointment:
    return Appointment(division="it", lead_id=lead.id, scheduled_at=scheduled, appointment_type="career_counselling", status=status,
                       appointment_code=f"CAP-{uuid.uuid4().hex[:8]}", booked_by_user_id=tel.id, created_at=created)


def meeting(tel, created, **over) -> BdmMeetingRequest:
    return BdmMeetingRequest(**({"code": f"MR-{uuid.uuid4().hex[:8]}", "requester_user_id": tel.id, "request_type": "college", "bdm_type": "college",
                                 "organization_name": "Govt College", "person_name": "Dr Rao", "contact_phone": "9876543210",
                                 "proposed_at": created + timedelta(days=1), "mode": "In person", "purpose": "Partnership", "created_at": created} | over))


async def test_a_day_with_no_activity_is_all_zeros(db_session):
    _, tel, _ = await team(db_session)
    now, today, _, _ = await clock(db_session)
    counts = await metrics.daily_activity(db_session, tel.id, today, now)
    assert set(counts) == set(metrics.ACTIVITY_KEYS) and all(v == 0 for v in counts.values())


async def test_calls_split_into_connected_and_not_connected_on_the_ist_day_only(db_session):
    _, tel, other = await team(db_session)
    now, today, start, end = await clock(db_session)
    lead = await make_lead(db_session, tel)
    await add(db_session,
              call(lead, tel, start), call(lead, tel, start + timedelta(minutes=1), "busy"), call(lead, tel, start + timedelta(minutes=2), "wrong_number"),
              call(lead, tel, start - timedelta(seconds=1)),  # 23:59:59 IST yesterday
              call(lead, other, start + timedelta(minutes=3)))  # someone else's call
    counts = await metrics.daily_activity(db_session, tel.id, today, now)
    assert (counts["calls"], counts["connected_calls"], counts["not_connected"]) == (3, 1, 2)
    yesterday = await metrics.daily_activity(db_session, tel.id, today - timedelta(days=1), now)
    assert yesterday["calls"] == 1 and yesterday["connected_calls"] == 1


async def test_follow_ups_completed_and_pending_at_end_of_day(db_session):
    _, tel, _ = await team(db_session)
    now, today, start, end = await clock(db_session)
    yday = today - timedelta(days=1)
    ystart, yend = day_range(yday)
    lead = await make_lead(db_session, tel, created_at=ystart - timedelta(days=1))
    await add(db_session,
              follow_up(lead, tel, ystart + timedelta(hours=1), created_at=ystart, status="done", completed_at=ystart + timedelta(hours=2), completed_by_user_id=tel.id),
              # open at the end of yesterday (done today): pending yesterday, completed today
              follow_up(lead, tel, ystart + timedelta(hours=3), created_at=ystart, status="done", completed_at=start + timedelta(minutes=1), completed_by_user_id=tel.id),
              # due tomorrow: never pending yesterday
              follow_up(lead, tel, end + timedelta(hours=1), created_at=ystart),
              # cancelled before yesterday ended
              follow_up(lead, tel, ystart + timedelta(hours=4), created_at=ystart, status="cancelled", cancelled_at=ystart + timedelta(hours=5), cancel_reason="x"))
    y = await metrics.daily_activity(db_session, tel.id, yday, now)
    assert (y["follow_ups_completed"], y["follow_ups_pending"]) == (1, 1)
    t = await metrics.daily_activity(db_session, tel.id, today, now)
    assert t["follow_ups_completed"] == 1


async def test_appointments_messages_and_qualified_are_mine_on_the_day(db_session):
    _, tel, other = await team(db_session)
    now, today, start, _ = await clock(db_session)
    lead = await make_lead(db_session, tel)
    lead2 = await make_lead(db_session, tel)
    await add(db_session,
              lead_appt(lead, tel, start + timedelta(days=2), start + timedelta(minutes=5), status="cancelled"),  # created today, counts
              lead_appt(lead2, other, start + timedelta(days=2), start + timedelta(minutes=5)),  # booked by someone else
              meeting(tel, start + timedelta(minutes=6)), meeting(tel, start - timedelta(hours=1)),
              LeadMessage(lead_id=lead.id, sender_user_id=tel.id, channel="whatsapp", body="Hi", sent_at=start + timedelta(minutes=7)),
              LeadMessage(lead_id=lead.id, sender_user_id=tel.id, channel="email", subject="S", body="Hi", delivery_status="sent", sent_at=start + timedelta(minutes=7)),
              history(lead, "qualified", tel, start + timedelta(minutes=8)), history(lead2, "qualified", other, start + timedelta(minutes=8)),
              history(lead2, "interested", tel, start + timedelta(minutes=9)))
    counts = await metrics.daily_activity(db_session, tel.id, today, now)
    assert (counts["counselor_appointments"], counts["bdm_appointments"], counts["new_appointments"]) == (1, 1, 2)
    assert counts["whatsapp_messages"] == 1 and counts["qualified_leads"] == 1


async def test_leads_assigned_and_hot_are_point_in_time_at_end_of_day(db_session):
    """DB4: yesterday's figures come from history -- a lead reassigned, closed or re-prioritised today still counts as it was."""
    _, tel, other = await team(db_session)
    now, today, start, _ = await clock(db_session)
    yday = today - timedelta(days=1)
    ystart, _ = day_range(yday)
    created = ystart - timedelta(days=1)
    moved = await make_lead(db_session, other, created_at=created, priority="warm")  # mine until today, then given to `other`
    closed = await make_lead(db_session, tel, created_at=created, status="not_interested")  # closed only today
    hot_later = await make_lead(db_session, tel, created_at=created, priority="hot")  # became hot only today
    closed_before = await make_lead(db_session, tel, created_at=created, status="lost")
    tomorrow_lead = await make_lead(db_session, tel)  # created today: not part of yesterday
    await add(db_session,
              assign(moved, created, None, tel), assign(moved, start + timedelta(minutes=1), tel, other),
              audit("lead.priority_change", moved, ystart, tel, **{"from": "warm", "to": "hot"}),
              audit("lead.priority_change", moved, start + timedelta(minutes=2), tel, **{"from": "hot", "to": "warm"}),
              history(closed, "not_interested", tel, start + timedelta(minutes=3), from_stage="contacted"),
              audit("lead.priority_change", hot_later, start + timedelta(minutes=4), tel, **{"from": "cold", "to": "hot"}),
              history(closed_before, "lost", tel, created + timedelta(minutes=1), from_stage="contacted"))
    y = await metrics.daily_activity(db_session, tel.id, yday, now)
    assert (y["leads_assigned"], y["hot_leads"]) == (3, 1)  # moved (hot), closed, hot_later (cold then)
    t = await metrics.daily_activity(db_session, tel.id, today, await db_now(db_session))  # after the leads were made
    assert (t["leads_assigned"], t["hot_leads"]) == (2, 1)  # hot_later + tomorrow_lead
    assert tomorrow_lead.id


async def test_a_conversion_is_credited_to_the_telecaller_at_conversion_and_dropped_after_an_unlink(db_session):
    """DB2 + tel-018 HO2."""
    _, tel, other = await team(db_session)
    now, today, start, _ = await clock(db_session)
    kept = await make_lead(db_session, other, status="converted")  # converted while mine, reassigned afterwards
    unlinked = await make_lead(db_session, tel, status="follow_up")  # converted today, then unlinked by an admin
    theirs = await make_lead(db_session, tel, status="converted")  # converted while `other` held it
    await add(db_session,
              assign(kept, start - timedelta(days=3), None, tel), history(kept, "converted", None, start + timedelta(minutes=1), "application_enrollment", "converted"),
              assign(kept, start + timedelta(minutes=2), tel, other),
              history(unlinked, "converted", None, start + timedelta(minutes=1), "application_enrollment", "converted"),
              history(unlinked, "follow_up", None, start + timedelta(minutes=2), "converted", "student_unlinked"),
              assign(theirs, start - timedelta(days=3), None, other), history(theirs, "converted", None, start + timedelta(minutes=1), "application_enrollment", "converted"),
              assign(theirs, start + timedelta(minutes=3), other, tel))
    counts = await metrics.daily_activity(db_session, tel.id, today, now)
    assert counts["converted_leads"] == 1
    assert (await metrics.daily_activity(db_session, other.id, today, now))["converted_leads"] == 1


async def test_tiles_count_today_for_the_telecaller(db_session):
    _, tel, other = await team(db_session)
    now, today, start, end = await clock(db_session)
    earlier = start - timedelta(days=2)
    fresh = await make_lead(db_session, tel, status="assigned")  # B1 (assigned today), B2 to-do
    mine_new = await make_lead(db_session, tel, status="first_call_pending", stage_changed_at=now - timedelta(hours=25), created_at=earlier)  # B2, B9 stale
    pending_new = await make_lead(db_session, tel, status="first_call_pending", stage_changed_at=now - timedelta(hours=1), created_at=earlier)  # B2 only
    hot = await make_lead(db_session, tel, status="interested", priority="hot", created_at=earlier)  # B4
    hot_handed = await make_lead(db_session, tel, status="interested", priority="hot", owner_id=other.id, created_at=earlier)  # handed over: not B4
    hot_closed = await make_lead(db_session, tel, status="lost", priority="hot", created_at=earlier)
    reassigned_away = await make_lead(db_session, other, created_at=earlier)
    await add(db_session,
              assign(fresh, now - timedelta(minutes=5), None, tel), assign(reassigned_away, now - timedelta(minutes=5), None, tel),
              assign(reassigned_away, now - timedelta(minutes=4), tel, other),
              follow_up(hot, tel, start + timedelta(seconds=1)),  # due today (and already past: overdue too if now > it)
              follow_up(hot, tel, end + timedelta(hours=2)),  # tomorrow
              follow_up(hot, tel, start - timedelta(hours=3)),  # overdue from yesterday
              call(hot, tel, now - timedelta(minutes=1)), call(hot, tel, now - timedelta(minutes=1), "busy"),
              TelTarget(scope="user", user_id=tel.id, period="daily", kpi="calls", value=80, effective_from=today - timedelta(days=1), set_by_user_id=other.id))
    tiles = await metrics.tiles(db_session, tel.id, "it", now)
    assert tiles["new_leads"] == 1
    assert tiles["calls_today"] == {"done": 2, "to_do": 3 + 1}
    assert tiles["follow_ups_due"] == 1 and tiles["hot_leads"] == 1
    assert (tiles["connected"], tiles["not_connected"]) == (1, 1)
    assert tiles["overdue"] == 2 + 1  # two follow-ups past due + one stale first-call lead
    assert tiles["daily_target"] == {"achieved": 2, "target": 80}
    assert pending_new.id and mine_new.id and hot_handed.id and hot_closed.id


async def test_b5_counts_my_appointments_and_accepted_bdm_meetings_for_today_and_lists_them(client, db_session):
    manager, tel, _ = await team(db_session)
    now, today, start, end = await clock(db_session)
    lead = await make_lead(db_session, tel, status="counselling_scheduled")
    lead2 = await make_lead(db_session, tel, status="counselling_scheduled")
    bdm_manager = await make_manager(db_session)
    bdm = await make_bdm(db_session, bdm_manager, "college")
    await as_user(client, bdm)
    org = await create_org(client)
    meet = await add(db_session, BdmAppointment(code=f"AP-{uuid.uuid4().hex[:8]}", bdm_user_id=bdm.id, organization_id=org["id"], contact_name="Dr Rao",
                                                starts_at=end - timedelta(minutes=30), appointment_type=BDM_APPOINTMENT_ALL_TYPES[0]))
    await add(db_session,
              lead_appt(lead, tel, end - timedelta(minutes=10), start - timedelta(days=1)),
              lead_appt(lead2, tel, end - timedelta(minutes=20), start - timedelta(days=1), status="cancelled"),
              meeting(tel, start - timedelta(days=1), status="accepted", bdm_user_id=bdm.id, bdm_appointment_id=meet.id, decided_at=start - timedelta(hours=1)),
              meeting(tel, start - timedelta(days=1)))  # still pending
    tiles = await metrics.tiles(db_session, tel.id, "it", now)
    assert tiles["appointments"] == 2
    listed = await metrics.appointments_today(db_session, tel.id, now)
    assert [(a["kind"], a["scheduled_at"]) for a in listed] == [("bdm", meet.starts_at), ("counselling", end - timedelta(minutes=10))]
    assert manager.id


async def test_target_progress_pairs_daily_and_month_to_date_achieved_with_targets(db_session):
    manager, tel, _ = await team(db_session)
    now, today, start, _ = await clock(db_session)
    lead = await make_lead(db_session, tel)
    month_start = day_range(today.replace(day=1))[0]
    rows = [call(lead, tel, now - timedelta(minutes=1))]
    if month_start < start:
        rows.append(call(lead, tel, month_start))  # earlier this month: monthly only
    await add(db_session, *rows,
              TelTarget(scope="user", user_id=tel.id, period="monthly", kpi="calls", value=1500, effective_from=today.replace(day=1), set_by_user_id=manager.id))
    progress = await metrics.target_progress(db_session, tel.id, "it", now)
    daily = {r["kpi"]: r for r in progress["daily"]}
    monthly = {r["kpi"]: r for r in progress["monthly"]}
    assert daily["calls"]["achieved"] == 1
    assert monthly["calls"] == {"kpi": "calls", "achieved": len(rows), "target": 1500}
    assert set(daily) == {"calls", "connected_calls", "qualified_leads", "follow_ups", "counselling_appointments", "conversions"}
