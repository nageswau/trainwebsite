"""upc-009 -- university meetings (spec §1-§3; AC1-AC3, P1, N1, E1, Q12, R1)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.models import AuditLog, PartnershipTask, UniversityMeeting
from app.services.bdm_travel import india_today
from tests.upc003_helpers import as_role, catalogue_country, create, login, make_head, make_pm, url

MEETINGS = "/api/v1/partnership/meetings"


def meeting_url(meeting_id, action: str | None = None) -> str:
    return f"{MEETINGS}/{meeting_id}" + (f"/{action}" if action else "")


def at(days: int, hour: int = 10) -> str:
    """An IST wall-clock time `days` from today, as the web sends it."""
    return f"{(india_today() + timedelta(days=days)).isoformat()}T{hour:02d}:00:00+05:30"


def day(offset: int) -> str:
    return (india_today() + timedelta(days=offset)).isoformat()


async def _owned(client, db):
    """A head creates a university and makes `pm` its primary manager. Returns (head, pm, other_pm, university), signed in as the head."""
    head = await make_head(db)
    pm, other = await make_pm(db, head), await make_pm(db, head)
    await login(client, head)
    uni = await create(client, (await catalogue_country(db)).id)
    response = await client.post(url(uni["id"], "assign"), json={"primary_manager_user_id": str(pm.id)})
    assert response.status_code == 200, response.text
    return head, pm, other, uni


async def _contact(client, university_id, name="Priya Raman", designation="Director, International Office") -> dict:
    response = await client.post(url(university_id, "contacts"), json={"name": name, "designation": designation})
    assert response.status_code == 201, response.text
    return response.json()["contact"]


def body(university_id, **overrides) -> dict:
    out = {"university_id": str(university_id), "meeting_type": "mou_discussion", "starts_at": at(3), "mode": "offline", "location": "Main campus, Room 4"}
    out.update(overrides)
    return out


async def schedule(client, university_id, expected: int = 201, **overrides) -> dict:
    response = await client.post(MEETINGS, json=body(university_id, **overrides))
    assert response.status_code == expected, response.text
    return response.json()["meeting"] if expected == 201 else response.json()


async def act(client, meeting_id, action: str, expected: int = 200, **payload) -> dict:
    response = await client.post(meeting_url(meeting_id, action), json=payload)
    assert response.status_code == expected, response.text
    return response.json()


async def _started(db, meeting_id) -> None:
    """Moves the start into the past -- the only way to record an outcome in a test (the API refuses a past start)."""
    await db.execute(update(UniversityMeeting).where(UniversityMeeting.id == uuid.UUID(meeting_id)).values(starts_at=datetime.now(UTC) - timedelta(hours=1)))
    await db.commit()


async def _stage(client, university_id) -> str:
    return (await client.get(url(university_id))).json()["university"]["pipeline"]["stage"]


async def _move(client, university_id, to_stage: str, note: str | None = None) -> None:
    current = await _stage(client, university_id)
    response = await client.post(url(university_id, "stage"), json={"from_stage": current, "to_stage": to_stage, "note": note})
    assert response.status_code == 200, response.text


# --- schedule (AC1, P1, N1, E1) --------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mou_discussion_with_two_university_participants_stores_every_field(client, db_session):
    """P1 + AC1: the §7 fields at scheduling; the contact's designation is copied; the contact person is a participant."""
    head, pm, other, uni = await _owned(client, db_session)
    await login(client, pm)
    priya, james = await _contact(client, uni["id"]), await _contact(client, uni["id"], "James Hart", "Head of Admissions")
    m = await schedule(
        client, uni["id"], contact_id=priya["id"], participant_contact_ids=[james["id"]], participant_user_ids=[str(other.id)],
        agenda="1. MoU clauses\n2. Intake", notes="Bring the draft MoU",
    )  # fmt: skip
    assert m["code"].startswith("UMT-") and m["status"] == "scheduled" and m["meeting_type"] == "mou_discussion"
    assert m["university"]["id"] == uni["id"] and m["mode"] == "offline" and m["location"] == "Main campus, Room 4"
    assert datetime.fromisoformat(m["starts_at"]) == datetime.fromisoformat(at(3))
    assert m["contact"] == {"id": priya["id"], "name": "Priya Raman", "designation": "Director, International Office"}
    assert {c["id"] for c in m["participants"]["contacts"]} == {priya["id"], james["id"]}
    assert [e["id"] for e in m["participants"]["employees"]] == [str(other.id)]
    assert m["responsible"]["id"] == str(pm.id) and m["created_by"]["id"] == str(pm.id)
    assert m["agenda"] == "1. MoU clauses\n2. Intake" and m["notes"] == "Bring the draft MoU" and m["warnings"] == []
    assert [e["event"] for e in m["events"]] == ["scheduled"] and m["follow_ups"] == []
    assert m["permissions"] == {"can_edit": True, "can_complete": False, "can_cancel": True}
    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == m["id"]))).all()
    assert [a.action for a in audit] == ["university_meeting.create"]
    assert "Bring the draft MoU" not in str(audit[0].metadata_json)  # never free text in audit
    assert (await client.get(meeting_url(m["id"]))).json()["meeting"]["id"] == m["id"]


@pytest.mark.asyncio
async def test_online_meeting_without_link_is_saved_with_a_warning(client, db_session):
    """E1 (MG4): allowed, with `link_missing`; a link clears it."""
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    m = await schedule(client, uni["id"], mode="online", location=None)
    assert m["warnings"] == ["link_missing"]
    response = await client.patch(meeting_url(m["id"]), json={"meeting_url": "https://meet.example.com/abc"})
    assert response.status_code == 200, response.text
    assert response.json()["meeting"]["warnings"] == [] and response.json()["meeting"]["meeting_url"] == "https://meet.example.com/abc"


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["contact_id", "participant_contact_ids"])
async def test_a_contact_of_another_university_is_422(client, db_session, field):
    """N1."""
    head, pm, _, uni = await _owned(client, db_session)
    other_uni = await create(client, (await catalogue_country(db_session)).id)  # still signed in as the head
    stranger = await _contact(client, other_uni["id"])
    await login(client, pm)
    value = stranger["id"] if field == "contact_id" else [stranger["id"]]
    detail = await schedule(client, uni["id"], 422, **{field: value})
    assert "contact" in str(detail).lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"starts_at": "2020-01-01T10:00:00+05:30"},  # MG3: in the past
        {"starts_at": "TOMORROW_FAR"},  # MG3: beyond 366 days
        {"meeting_type": "lunch"},
        {"mode": "hybrid"},
        {"meeting_url": "javascript:alert(1)"},  # MG4 / security: http(s) only
        {"status": "completed"},  # server-owned
        {"code": "UMT-999999"},
        {"discussion_points": "Too early"},  # set on complete only
        {"participant_contact_ids": [str(uuid.uuid4()) for _ in range(21)]},  # MG6: at most 20
        {"agenda": "x" * 2001},
    ],
)
async def test_invalid_schedules_are_422(client, db_session, overrides):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    if overrides.get("starts_at") == "TOMORROW_FAR":
        overrides = {"starts_at": at(400)}
    await schedule(client, uni["id"], 422, **overrides)


@pytest.mark.asyncio
async def test_employees_must_be_active_partnership_staff_other_than_the_responsible(client, db_session):
    """MG7."""
    head, pm, other, uni = await _owned(client, db_session)
    counselor = await as_role(client, db_session, "counselor", "overseas")
    await login(client, pm)
    await schedule(client, uni["id"], 422, participant_user_ids=[str(counselor.id)])
    await schedule(client, uni["id"], 422, participant_user_ids=[str(pm.id)])
    m = await schedule(client, uni["id"], participant_user_ids=[str(head.id), str(other.id)])
    assert {e["id"] for e in m["participants"]["employees"]} == {str(head.id), str(other.id)}


@pytest.mark.asyncio
async def test_responsible_employee_rule(client, db_session):
    """MG8: a manager is responsible for their own meetings; a head picks themselves or an active direct report."""
    head, pm, other, uni = await _owned(client, db_session)
    stranger_head = await make_head(db_session)
    outsider = await make_pm(db_session, stranger_head)
    await login(client, pm)
    await schedule(client, uni["id"], 422, responsible_user_id=str(other.id))
    await login(client, head)
    await schedule(client, uni["id"], 422, responsible_user_id=str(outsider.id))
    m = await schedule(client, uni["id"], responsible_user_id=str(pm.id))
    assert m["responsible"]["id"] == str(pm.id) and m["created_by"]["id"] == str(head.id)
    await login(client, pm)  # the responsible employee acts on it
    assert (await client.get(meeting_url(m["id"]))).json()["meeting"]["permissions"]["can_edit"] is True
    await login(client, other)  # a team-mate who is neither responsible nor the scheduler only reads
    assert (await client.get(meeting_url(m["id"]))).json()["meeting"]["permissions"] == {"can_edit": False, "can_complete": False, "can_cancel": False}
    response = await client.post(meeting_url(m["id"], "cancel"), json={"reason": "Not mine"})
    assert response.status_code == 403


# --- access (MG14, MG15, R1) -----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("role", [("overseas_admin", "overseas"), ("counselor", "overseas"), ("university_rep", "overseas")])
async def test_other_roles_are_403(client, db_session, role):
    await as_role(client, db_session, *role)
    assert (await client.get(MEETINGS)).status_code == 403
    assert (await client.post(MEETINGS, json=body(uuid.uuid4()))).status_code == 403


@pytest.mark.asyncio
async def test_super_admin_reads_every_meeting_but_does_not_schedule(client, db_session):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    m = await schedule(client, uni["id"])
    await as_role(client, db_session, "super_admin", "global")
    assert (await client.get(meeting_url(m["id"]))).json()["meeting"]["permissions"]["can_edit"] is False
    assert any(i["id"] == m["id"] for i in (await client.get(MEETINGS, params={"university_id": uni["id"]})).json()["items"])
    await schedule(client, uni["id"], 403)


@pytest.mark.asyncio
async def test_university_scope_and_state(client, db_session):
    """MG15: another team's manager is 403; an inactive university is 409; an unknown university 422; an unknown meeting 404."""
    head, pm, other, uni = await _owned(client, db_session)
    await login(client, other)  # same team but not an owner of this university
    await schedule(client, uni["id"], 403)
    await login(client, head)
    assert (await client.post(url(uni["id"], "deactivate"), json={})).status_code == 200
    await login(client, pm)
    await schedule(client, uni["id"], 409)
    await schedule(client, uuid.uuid4(), 422)
    assert (await client.get(meeting_url(uuid.uuid4()))).status_code == 404


# --- stage (AC3, MG13) -------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scheduling_moves_an_earlier_stage_to_meeting_scheduled(client, db_session):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    assert await _stage(client, uni["id"]) == "target_university"
    m = await schedule(client, uni["id"])
    assert await _stage(client, uni["id"]) == "meeting_scheduled"
    history = (await client.get(url(uni["id"], "stage-history"))).json()["items"]
    assert history[0]["to_stage"] == "meeting_scheduled" and m["code"] in history[0]["note"]
    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == uni["id"], AuditLog.action == "university.stage_changed"))).all()
    assert audit[-1].metadata_json["source"] == "meeting"


@pytest.mark.asyncio
async def test_scheduling_never_moves_a_later_or_lost_stage(client, db_session):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    await _move(client, uni["id"], "proposal_sent")
    await schedule(client, uni["id"])
    assert await _stage(client, uni["id"]) == "proposal_sent"
    await _move(client, uni["id"], "interested", note="Back to talks")
    assert (await client.post(url(uni["id"], "lost"), json={"reason": "Went quiet"})).status_code == 200
    await schedule(client, uni["id"])
    university = (await client.get(url(uni["id"]))).json()["university"]
    assert university["pipeline"]["stage"] == "interested" and university["pipeline"]["lost"] is not None


# --- edit / reschedule (MG9) ----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_reschedule_keeps_old_and_new_times_and_copies_a_new_contact(client, db_session):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    m = await schedule(client, uni["id"])
    james = await _contact(client, uni["id"], "James Hart", "Head of Admissions")
    response = await client.patch(meeting_url(m["id"]), json={"starts_at": at(5, 15), "reschedule_reason": "Dean travelling", "contact_id": james["id"]})
    assert response.status_code == 200, response.text
    out = response.json()["meeting"]
    assert out["contact"]["designation"] == "Head of Admissions" and james["id"] in {c["id"] for c in out["participants"]["contacts"]}
    resched = [e for e in out["events"] if e["event"] == "rescheduled"]
    assert len(resched) == 1 and resched[0]["reason"] == "Dean travelling" and resched[0]["old_starts_at"] == m["starts_at"]
    assert [e["event"] for e in out["events"]] == ["scheduled", "rescheduled", "edited"]
    assert (await client.patch(meeting_url(m["id"]), json={"starts_at": "2020-01-01T10:00:00+05:30"})).status_code == 422
    assert (await client.patch(meeting_url(m["id"]), json={"university_id": str(uuid.uuid4())})).status_code == 422
    same = await client.patch(meeting_url(m["id"]), json={"location": "Main campus, Room 4"})  # unchanged value: no new event
    assert len(same.json()["meeting"]["events"]) == 3


# --- complete (AC2, Q12, MG10-MG13) -------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_outcome_before_the_start_is_422(client, db_session):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    m = await schedule(client, uni["id"])
    await act(client, m["id"], "complete", 422, notes="Too early")


@pytest.mark.asyncio
async def test_completing_records_the_outcome_creates_follow_ups_and_moves_the_stage(client, db_session):
    """AC1 (outcome fields) + AC2 (next action → follow-up) + Q12 (next meeting date → follow-up) + AC3 (Meeting Completed)."""
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    m = await schedule(client, uni["id"])
    await _started(db_session, m["id"])
    assert (await client.get(meeting_url(m["id"]))).json()["meeting"]["permissions"]["can_complete"] is True
    out = (await act(
        client, m["id"], "complete", notes="Met the dean", discussion_points="Clauses 4-7", decisions="Exclusive for Kerala",
        next_action="Send the revised MoU", next_action_due_on=day(2), next_meeting_date=day(30),
    ))["meeting"]  # fmt: skip
    assert out["status"] == "completed" and out["completed_by"]["id"] == str(pm.id) and out["completed_at"]
    assert (out["notes"], out["discussion_points"], out["decisions"]) == ("Met the dean", "Clauses 4-7", "Exclusive for Kerala")
    assert (out["next_action"], out["next_action_due_on"], out["next_meeting_date"]) == ("Send the revised MoU", day(2), day(30))
    assert out["permissions"] == {"can_edit": False, "can_complete": False, "can_cancel": False}
    follow_ups = {f["title"]: f for f in out["follow_ups"]}
    assert set(follow_ups) == {"Send the revised MoU", "Schedule the next meeting"}
    assert follow_ups["Send the revised MoU"]["due_on"] == day(2) and follow_ups["Schedule the next meeting"]["due_on"] == day(30)
    tasks = (await db_session.scalars(select(PartnershipTask).where(PartnershipTask.rule.like(f"meeting:{m['id']}%")))).all()
    assert {(t.source, t.kind, t.assignee_user_id, t.priority) for t in tasks} == {("meeting", "follow_up", pm.id, "high"), ("meeting", "follow_up", pm.id, "medium")}
    assert await _stage(client, uni["id"]) == "meeting_completed"
    stage_task = await db_session.scalar(select(PartnershipTask).where(PartnershipTask.university_id == uuid.UUID(uni["id"]), PartnershipTask.rule == "stage:meeting_completed"))
    assert stage_task is not None and stage_task.title == "Send partnership proposal"  # upc-020's stage rule fires
    assert [e["event"] for e in out["events"]] == ["scheduled", "completed"]
    await act(client, m["id"], "complete", 409, notes="Again")


@pytest.mark.asyncio
async def test_completing_without_a_next_action_creates_no_task(client, db_session):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    m = await schedule(client, uni["id"])
    await _started(db_session, m["id"])
    out = (await act(client, m["id"], "complete", decisions="None yet"))["meeting"]
    assert out["follow_ups"] == [] and out["next_action"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {},  # MG10: something must be recorded
        {"notes": "  "},
        {"notes": "Met", "next_action": "Send MoU"},  # MG11: a next action needs its due date
        {"notes": "Met", "next_action_due_on": "TODAY"},  # ... and a due date needs a next action
        {"notes": "Met", "next_action": "Send MoU", "next_action_due_on": "YESTERDAY"},
        {"notes": "Met", "next_meeting_date": "YESTERDAY"},
        {"notes": "Met", "next_action": "x" * 201, "next_action_due_on": "TODAY"},
    ],
)
async def test_invalid_outcomes_are_422(client, db_session, payload):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    m = await schedule(client, uni["id"])
    await _started(db_session, m["id"])
    words = {"TODAY": day(0), "YESTERDAY": day(-1)}
    await act(client, m["id"], "complete", 422, **{k: words.get(v, v) for k, v in payload.items()})
    assert (await client.get(meeting_url(m["id"]))).json()["meeting"]["status"] == "scheduled"


# --- cancel (MG9) -----------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cancel_needs_a_reason_and_is_final(client, db_session):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    m = await schedule(client, uni["id"])
    await act(client, m["id"], "cancel", 422, reason=" ")
    out = (await act(client, m["id"], "cancel", reason="Dean unavailable"))["meeting"]
    assert out["status"] == "cancelled" and out["cancel_reason"] == "Dean unavailable" and out["cancelled_at"]
    assert out["events"][-1]["event"] == "cancelled" and out["events"][-1]["reason"] == "Dean unavailable"
    await act(client, m["id"], "cancel", 409, reason="Again")
    await _started(db_session, m["id"])
    await act(client, m["id"], "complete", 409, notes="Late")
    assert (await client.patch(meeting_url(m["id"]), json={"location": "Elsewhere"})).status_code == 409


# --- lists (MG16) -------------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_views_counts_and_filters(client, db_session):
    head, pm, other, uni = await _owned(client, db_session)
    await login(client, pm)
    soon, later = await schedule(client, uni["id"], starts_at=at(1)), await schedule(client, uni["id"], starts_at=at(9))
    waiting = await schedule(client, uni["id"])
    done = await schedule(client, uni["id"])
    called_off = await schedule(client, uni["id"], participant_user_ids=[str(other.id)])
    await _started(db_session, waiting["id"])
    await _started(db_session, done["id"])
    await act(client, done["id"], "complete", notes="Fine")
    await act(client, called_off["id"], "cancel", reason="Postponed")
    page = (await client.get(MEETINGS, params={"university_id": uni["id"], "view": "upcoming"})).json()
    assert [i["id"] for i in page["items"]] == [soon["id"], later["id"]]
    assert page["counts"] == {"upcoming": 2, "awaiting_outcome": 1, "completed": 1, "cancelled": 1}
    assert [i["id"] for i in (await client.get(MEETINGS, params={"university_id": uni["id"], "view": "awaiting_outcome"})).json()["items"]] == [waiting["id"]]
    every = (await client.get(MEETINGS, params={"university_id": uni["id"]})).json()
    assert every["total"] == 5 and [i["status"] for i in every["items"]][:3] == ["scheduled"] * 3  # scheduled first
    await login(client, other)
    mine = (await client.get(MEETINGS, params={"university_id": uni["id"], "mine": "true", "view": "cancelled"})).json()
    assert [i["id"] for i in mine["items"]] == [called_off["id"]]  # an EduSphere participant counts as "mine"
    assert (await client.get(MEETINGS, params={"view": "someday"})).status_code == 422
