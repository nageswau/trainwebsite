"""mgmt-029 -- management meetings + minutes chain (spec MM1-MM14; AC: a meeting's minutes show their decisions and tasks, with
completion status rolled up)."""

import datetime
import uuid
from datetime import UTC, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.models import AuditLog, ManagementDiscussion, ManagementMeeting, ManagementTask, Notification
from tests.bdm001_helpers import login, make_user

MEETINGS = "/api/v1/management/meetings"
MINE = "/api/v1/me/management-meetings"
IST = ZoneInfo("Asia/Kolkata")
TODAY = datetime.datetime.now(IST).date()
KINDS = ("partner", "department", "school", "university", "agent", "recruiter", "marketing_review")


def at(day: datetime.date, hour: int = 10, minute: int = 0) -> str:
    return datetime.datetime.combine(day, datetime.time(hour, minute), IST).isoformat()


def soon() -> str:
    """A start in the near future (whole minutes)."""
    return (datetime.datetime.now(UTC) + timedelta(hours=2)).replace(second=0, microsecond=0).isoformat()


def started() -> str:
    """A start already passed (whole minutes), so minutes may be recorded."""
    return (datetime.datetime.now(UTC) - timedelta(hours=2)).replace(second=0, microsecond=0).isoformat()


async def as_user(client, db, role: str = "partner", division: str = "global", **kwargs):
    user = await make_user(db, role, division, **kwargs)
    await login(client, user)
    return user


def body(**overrides) -> dict:
    data = {"title": "Monthly partner meeting", "kind": "partner", "starts_at": soon(), "mode": "Online", "meeting_url": "https://meet.example.com/abc"}
    data.update(overrides)
    return data


async def create(client, data: dict) -> dict:
    response = await client.post(MEETINGS, json=data)
    assert response.status_code == 201, response.text
    return response.json()


async def held(client, db, **overrides) -> dict:
    """A meeting that has started, with minutes recorded."""
    meeting = await create(client, body(starts_at=started(), **overrides))
    response = await client.post(f"{MEETINGS}/{meeting['id']}/minutes", json={"minutes": "Reviewed the quarter.\nAgreed the Japan plan."})
    assert response.status_code == 200, response.text
    return response.json()


async def notes_for(db, user_id) -> list[Notification]:
    db.expire_all()
    return list((await db.scalars(select(Notification).where(Notification.user_id == user_id).order_by(Notification.created_at))).all())


# --- create / read (MM1-MM5) ---------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_partner_schedules_each_of_the_seven_kinds(client, db_session):
    member = await make_user(db_session, "trainer", "it", name="Ravi Trainer")
    partner = await as_user(client, db_session)
    for kind in KINDS:
        created = await create(client, body(kind=kind, participant_ids=[str(member.id)], agenda="1. Targets\n2. Hiring", location="Board room"))
        assert created["kind"] == kind and created["status"] == "scheduled" and created["minutes"] is None
        assert [p["full_name"] for p in created["participants"]] == ["Ravi Trainer"]
        assert created["agenda"] == "1. Targets\n2. Hiring" and created["created_by"]["id"] == str(partner.id)
        assert created["decisions"] == [] and created["tasks"] == [] and created["progress"] == {"done": 0, "total": 0}
    assert (await client.get(f"{MEETINGS}/{created['id']}")).json()["id"] == created["id"]


@pytest.mark.asyncio
async def test_field_rules(client, db_session):
    inactive = await make_user(db_session, "trainer", "it", active=False)
    student = await make_user(db_session, "it_student", "it")
    await as_user(client, db_session)
    bad_link = await client.post(MEETINGS, json=body(meeting_url="javascript:alert(1)"))
    assert bad_link.status_code == 422 and bad_link.json()["detail"][0]["loc"] == ["body", "meeting_url"]
    for person in (inactive, student):
        refused = await client.post(MEETINGS, json=body(participant_ids=[str(person.id)]))
        assert refused.status_code == 422 and refused.json()["detail"][0]["loc"] == ["body", "participant_ids"]
    far = await client.post(MEETINGS, json=body(starts_at=at(TODAY + timedelta(days=400))))
    assert far.status_code == 422 and far.json()["detail"][0]["loc"] == ["body", "starts_at"]
    assert (await client.post(MEETINGS, json=body(kind="board"))).status_code == 422
    assert (await client.post(MEETINGS, json=body(title="x"))).status_code == 422
    assert (await client.post(MEETINGS, json=body(mode="Carrier pigeon"))).status_code == 422
    assert (await client.post(MEETINGS, json={**body(), "status": "completed"})).status_code == 422  # never on create
    assert (await client.get(f"{MEETINGS}/{uuid.uuid4()}")).status_code == 404


@pytest.mark.asyncio
async def test_super_admin_may_manage_meetings_accountant_and_staff_may_not(client, db_session):
    await as_user(client, db_session, "super_admin")
    created = await create(client, body())
    for role, division in (("accountant", "global"), ("bdm", "it"), ("trainer", "it")):
        await as_user(client, db_session, role, division)
        assert (await client.get(MEETINGS)).status_code == 403
        assert (await client.post(MEETINGS, json=body())).status_code == 403
        assert (await client.get(f"{MEETINGS}/{created['id']}")).status_code == 403
        assert (await client.patch(f"{MEETINGS}/{created['id']}", json={"title": "Changed"})).status_code == 403
        assert (await client.post(f"{MEETINGS}/{created['id']}/minutes", json={"minutes": "Notes"})).status_code == 403
        assert (await client.get(f"{MEETINGS}/options")).status_code == 403


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    assert (await client.get(MEETINGS)).status_code == 401
    assert (await client.get(MINE)).status_code == 401


# --- calendar + today (MM11) -----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_calendar_lists_by_ist_day_and_defaults_to_today(client, db_session):
    await as_user(client, db_session)
    tag = uuid.uuid4().hex[:6]
    day = TODAY + timedelta(days=30)
    early = await create(client, body(title=f"Early {tag}", starts_at=at(day, 0, 15)))  # 00:15 IST is the previous UTC day
    late = await create(client, body(title=f"Late {tag}", starts_at=at(day, 23, 45)))
    await create(client, body(title=f"Next {tag}", starts_at=at(day + timedelta(days=1), 9)))
    page = (await client.get(MEETINGS, params={"date_from": day.isoformat(), "date_to": day.isoformat()})).json()
    mine = [i for i in page["items"] if tag in i["title"]]
    assert [i["id"] for i in mine] == [early["id"], late["id"]]
    assert page["date_from"] == day.isoformat() and page["today"] == TODAY.isoformat()
    today = (await client.get(MEETINGS)).json()
    assert today["date_from"] == today["date_to"] == TODAY.isoformat()
    assert all(tag not in i["title"] for i in today["items"])
    kinds = (await client.get(MEETINGS, params={"date_from": day.isoformat(), "date_to": day.isoformat(), "kind": "school"})).json()
    assert all(i["kind"] == "school" for i in kinds["items"])
    assert (await client.get(MEETINGS, params={"date_from": day.isoformat(), "date_to": (day + timedelta(days=70)).isoformat()})).status_code == 422
    assert (await client.get(MEETINGS, params={"date_from": day.isoformat(), "date_to": (day - timedelta(days=1)).isoformat()})).status_code == 422


# --- edit / cancel (MM4, MM7) ----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_edit_reschedule_and_cancel(client, db_session):
    await as_user(client, db_session)
    created = await create(client, body())
    moved = await client.patch(f"{MEETINGS}/{created['id']}", json={"starts_at": at(TODAY + timedelta(days=3), 15), "meeting_url": None})
    assert moved.status_code == 200 and moved.json()["meeting_url"] is None
    assert (await client.patch(f"{MEETINGS}/{created['id']}", json={"title": None})).status_code == 422
    cancelled = await client.patch(f"{MEETINGS}/{created['id']}", json={"status": "cancelled"})
    assert cancelled.json()["status"] == "cancelled"
    assert (await client.patch(f"{MEETINGS}/{created['id']}", json={"title": "Back on"})).status_code == 409
    assert (await client.post(f"{MEETINGS}/{created['id']}/minutes", json={"minutes": "Notes"})).status_code == 409
    assert (await client.patch(f"{MEETINGS}/{created['id']}", json={"status": "completed"})).status_code == 422  # only minutes complete


# --- minutes (MM6) --------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_minutes_complete_a_started_meeting_and_can_be_edited(client, db_session):
    await as_user(client, db_session)
    future = await create(client, body())
    early = await client.post(f"{MEETINGS}/{future['id']}/minutes", json={"minutes": "Too soon"})
    assert early.status_code == 409
    meeting = await held(client, db_session)
    assert meeting["status"] == "completed" and meeting["minutes"].startswith("Reviewed") and meeting["minutes_recorded_at"]
    first_stamp = meeting["minutes_recorded_at"]
    edited = (await client.post(f"{MEETINGS}/{meeting['id']}/minutes", json={"minutes": "Corrected minutes"})).json()
    assert edited["minutes"] == "Corrected minutes" and edited["minutes_recorded_at"] == first_stamp
    assert (await client.post(f"{MEETINGS}/{meeting['id']}/minutes", json={"minutes": " "})).status_code == 422
    assert (await client.patch(f"{MEETINGS}/{meeting['id']}", json={"starts_at": soon()})).status_code == 409
    assert (await client.patch(f"{MEETINGS}/{meeting['id']}", json={"status": "cancelled"})).status_code == 409
    renamed = await client.patch(f"{MEETINGS}/{meeting['id']}", json={"title": "Partner meeting — October"})
    assert renamed.status_code == 200
    db_session.expire_all()
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == meeting["id"]).order_by(AuditLog.created_at))).all()
    assert [r.action for r in rows] == ["mgmt.meeting.create", "mgmt.meeting.complete", "mgmt.meeting.update", "mgmt.meeting.update"]
    assert rows[1].metadata_json == {"fields": ["minutes"]}
    assert "Reviewed" not in str([r.metadata_json for r in rows])


# --- the chain (MM8-MM10, AC) ----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_chain_needs_minutes(client, db_session):
    owner = await make_user(db_session, "trainer", "it")
    await as_user(client, db_session)
    meeting = await create(client, body(starts_at=started()))
    assert (await client.post(f"{MEETINGS}/{meeting['id']}/decisions", json={"decision": "Proceed"})).status_code == 409
    task = {"title": "Draft plan", "owner_user_id": str(owner.id), "priority": "high", "deadline": TODAY.isoformat()}
    assert (await client.post(f"{MEETINGS}/{meeting['id']}/tasks", json=task)).status_code == 409


@pytest.mark.asyncio
async def test_ac_minutes_show_their_decisions_and_tasks_with_completion_rolled_up(client, db_session):
    responsible = await make_user(db_session, "partnership_manager", "global", name="Meera Partnership")
    owner = await make_user(db_session, "trainer", "it", name="Ravi Trainer")
    gone = await make_user(db_session, "counselor", "overseas")
    partner = await as_user(client, db_session)
    meeting = await held(client, db_session, participant_ids=[str(responsible.id), str(gone.id)])
    gone.active = False
    await db_session.commit()

    decided = await client.post(
        f"{MEETINGS}/{meeting['id']}/decisions", json={"decision": "Proceed with Japan agreement", "responsible_user_id": str(responsible.id), "deadline": (TODAY + timedelta(days=5)).isoformat()}
    )
    assert decided.status_code == 201, decided.text
    chain = decided.json()
    decision = chain["decisions"][0]
    assert decision["decision"] == "Proceed with Japan agreement" and decision["responsible"]["full_name"] == "Meera Partnership"
    discussion = await db_session.get(ManagementDiscussion, uuid.UUID(decision["id"]))
    assert discussion.meeting_id == uuid.UUID(meeting["id"]) and discussion.topic == meeting["title"]
    assert discussion.discussion_date == datetime.datetime.fromisoformat(meeting["starts_at"]).astimezone(IST).date()

    task_body = {"title": "Send the draft MoU", "owner_user_id": str(owner.id), "priority": "high", "deadline": TODAY.isoformat(), "decision_id": decision["id"]}
    under_decision = await client.post(f"{MEETINGS}/{meeting['id']}/tasks", json=task_body)
    assert under_decision.status_code == 201, under_decision.text
    direct = await client.post(f"{MEETINGS}/{meeting['id']}/tasks", json={**task_body, "title": "Book the next review", "decision_id": None})
    chain = direct.json()
    assert [t["title"] for t in chain["decisions"][0]["tasks"]] == ["Send the draft MoU"]
    assert [t["title"] for t in chain["tasks"]] == ["Book the next review"]
    assert chain["progress"] == {"done": 0, "total": 3}

    ids = [uuid.UUID(t["id"]) for t in chain["tasks"] + chain["decisions"][0]["tasks"]]
    tasks = (await db_session.scalars(select(ManagementTask).where(ManagementTask.id.in_(ids)))).all()
    by_title = {t.title: t for t in tasks}
    assert (by_title["Send the draft MoU"].source, by_title["Send the draft MoU"].source_id) == ("decision", discussion.id)
    assert (by_title["Book the next review"].source, by_title["Book the next review"].source_id) == ("meeting", uuid.UUID(meeting["id"]))

    # the owner completes their task in their own Management tasks -> the meeting's roll-up moves
    await login(client, owner)
    done = await client.patch(f"/api/v1/me/management-tasks/{by_title['Send the draft MoU'].id}", json={"status": "completed"})
    assert done.status_code == 200
    await login(client, partner)
    detail = (await client.get(f"{MEETINGS}/{meeting['id']}")).json()
    assert detail["progress"] == {"done": 1, "total": 3}
    assert detail["decisions"][0]["tasks"][0]["status"] == "completed"
    # a cancelled item leaves the roll-up
    await client.patch(f"/api/v1/management/tasks/{by_title['Book the next review'].id}", json={"status": "cancelled"})
    assert (await client.get(f"{MEETINGS}/{meeting['id']}")).json()["progress"] == {"done": 1, "total": 2}
    # the decision's own discussion page points back at the meeting
    assert (await client.get(f"/api/v1/management/discussions/{decision['id']}")).json()["meeting_id"] == meeting["id"]
    owner_id = owner.id
    assert [n.title for n in await notes_for(db_session, responsible.id)][-1] == "A management decision was assigned to you"
    assert [n.title for n in await notes_for(db_session, owner_id)][:2] == ["A management task was assigned to you"] * 2


@pytest.mark.asyncio
async def test_chain_rules(client, db_session):
    owner = await make_user(db_session, "trainer", "it")
    await as_user(client, db_session)
    meeting = await held(client, db_session)
    other = await held(client, db_session)
    other_decision = (await client.post(f"{MEETINGS}/{other['id']}/decisions", json={"decision": "Hire two trainers"})).json()["decisions"][0]
    wrong = await client.post(
        f"{MEETINGS}/{meeting['id']}/tasks", json={"title": "Post the job", "owner_user_id": str(owner.id), "priority": "low", "deadline": TODAY.isoformat(), "decision_id": other_decision["id"]}
    )
    assert wrong.status_code == 422 and wrong.json()["detail"][0]["loc"] == ["body", "decision_id"]
    past = await client.post(
        f"{MEETINGS}/{meeting['id']}/tasks", json={"title": "Post the job", "owner_user_id": str(owner.id), "priority": "low", "deadline": (TODAY - timedelta(days=1)).isoformat()}
    )
    assert past.status_code == 422 and past.json()["detail"][0]["loc"] == ["body", "deadline"]
    student = await make_user(db_session, "it_student", "it")
    refused = await client.post(f"{MEETINGS}/{meeting['id']}/decisions", json={"decision": "Proceed", "responsible_user_id": str(student.id)})
    assert refused.status_code == 422 and refused.json()["detail"][0]["loc"] == ["body", "responsible_user_id"]
    assert (await client.post(f"{MEETINGS}/{meeting['id']}/decisions", json={"decision": "x"})).status_code == 422
    assert (await client.post(f"{MEETINGS}/{uuid.uuid4()}/decisions", json={"decision": "Proceed"})).status_code == 404


# --- participants (MM12, MM13) -------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_participant_sees_their_meetings_without_minutes(client, db_session):
    member = await make_user(db_session, "counselor", "overseas")
    outsider = await make_user(db_session, "trainer", "it")
    await as_user(client, db_session)
    upcoming = await create(client, body(participant_ids=[str(member.id)], agenda="Targets"))
    recorded = await held(client, db_session, participant_ids=[str(member.id)])
    await create(client, body(title="Not invited"))
    await login(client, member)
    mine = (await client.get(MINE)).json()
    by_id = {i["id"]: i for i in mine["items"]}
    assert set(by_id) == {upcoming["id"], recorded["id"]}
    assert set(by_id[upcoming["id"]]) == {"id", "title", "kind", "starts_at", "mode", "location", "meeting_url", "agenda", "status"}
    assert "minutes" not in str(mine)
    await login(client, outsider)
    assert (await client.get(MINE)).json()["items"] == []


@pytest.mark.asyncio
async def test_participants_are_notified_when_added_rescheduled_or_cancelled(client, db_session):
    first = (await make_user(db_session, "trainer", "it")).id
    second = (await make_user(db_session, "counselor", "overseas")).id
    partner = (await as_user(client, db_session)).id  # plain ids: notes_for expires the session's objects
    created = await create(client, body(participant_ids=[str(first), str(partner)]))
    assert [n.title for n in await notes_for(db_session, first)] == ["You were invited to a management meeting"]
    assert await notes_for(db_session, partner) == []  # never the actor
    await client.patch(f"{MEETINGS}/{created['id']}", json={"participant_ids": [str(first), str(second)]})
    assert [n.title for n in await notes_for(db_session, second)] == ["You were invited to a management meeting"]
    assert len(await notes_for(db_session, first)) == 1  # unchanged for an existing participant
    await client.patch(f"{MEETINGS}/{created['id']}", json={"starts_at": at(TODAY + timedelta(days=4), 11)})
    assert (await notes_for(db_session, first))[-1].title == "A management meeting was rescheduled"
    await client.patch(f"{MEETINGS}/{created['id']}", json={"status": "cancelled"})
    notes = await notes_for(db_session, second)
    assert notes[-1].title == "A management meeting was cancelled" and notes[-1].action_url == "/account/management-tasks#meetings"
    assert "meet.example.com" not in notes[-1].body


@pytest.mark.asyncio
async def test_meeting_rows_store_ist_minutes(client, db_session):
    await as_user(client, db_session)
    created = await create(client, body(starts_at=at(TODAY + timedelta(days=2), 9, 30)))
    row = await db_session.get(ManagementMeeting, uuid.UUID(created["id"]))
    assert row.starts_at.astimezone(IST).time() == datetime.time(9, 30)
    seconds = await create(client, body(starts_at=datetime.datetime.combine(TODAY + timedelta(days=2), datetime.time(9, 30, 15), IST).isoformat()))
    assert seconds["starts_at"] == created["starts_at"]  # seconds are dropped (bdm R-A7), as everywhere else
