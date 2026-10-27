"""nehn-037 part 4 (DEC-SCOPE-296, I1-I9) -- admission interviews on an overseas application: the counselor/admin writes, the readers,
the outcome-after-the-date rule, the cap, closed applications, unchanged saves, notices (CC5) and the audit. Agency world: agn023_helpers."""

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import ApplicationInterview, AuditLog
from tests.agn001_helpers import client_for, mk_user
from tests.agn023_helpers import ASSIGN, assign_world, fresh, notices

BASE = "/api/v1/workflows/overseas/applications/{}/interviews"
ONE = BASE + "/{}"
MINE = "/api/v1/workflows/overseas/student/interviews"
PAST = datetime.now(UTC) - timedelta(days=2)
FUTURE = datetime.now(UTC) + timedelta(days=5)


def body(when: datetime = FUTURE, **overrides) -> dict:
    return {"scheduled_at": when.isoformat(), "mode": "online", "location": "https://meet.example.edu/abc", "student_note": "Have your passport ready."} | overrides


@pytest_asyncio.fixture
async def world(db_session):
    w = await assign_world(db_session, status="submitted")
    async with client_for(w["admin"].email) as c:
        for app in (w["app"], w["direct_app"]):
            assert (await c.put(ASSIGN.format(app.id), json={"counselor_id": str(w["counselor"].id)})).status_code == 200
    return w


async def _rows(db, app) -> list[ApplicationInterview]:
    stmt = select(ApplicationInterview).where(ApplicationInterview.application_id == app.id).order_by(ApplicationInterview.created_at, ApplicationInterview.id)
    return list((await db.scalars(stmt.execution_options(populate_existing=True))).all())


async def _titles(db, user) -> list[str]:
    return [n.title for n in await notices(db, user)]


@pytest.mark.asyncio
async def test_the_counselor_schedules_an_interview_the_student_sees_it_and_is_told(db_session, world):  # AC3
    app, student = world["direct_app"], world["direct_student"]
    async with client_for(world["counselor"].email) as c:
        r = await c.post(BASE.format(app.id), json=body())
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["changed"] is True
    view = data["interview"]
    assert (view["mode"], view["mode_label"], view["outcome"], view["outcome_label"]) == ("online", "Online", None, "Awaiting result")
    assert view["location"] == "https://meet.example.edu/abc" and view["student_note"] == "Have your passport ready."
    assert view["recorded_by"] == world["counselor"].full_name
    [row] = await _rows(db_session, app)
    assert (row.created_by_id, row.updated_by_id) == (world["counselor"].id, world["counselor"].id)
    item = await fresh(db_session, app)
    assert (item.status, item.sub_status) == ("submitted", None)  # I8: no stage move
    assert "Interview scheduled" in await _titles(db_session, student)
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(app.id), AuditLog.action == "overseas.application.interview"))
    assert audit.metadata_json["interview_id"] == str(row.id) and audit.metadata_json["action"] == "added"
    async with client_for(student.email) as c:
        mine = await c.get(MINE)
        listed = await c.get(BASE.format(app.id))
    assert mine.status_code == 200 and listed.status_code == 200
    [entry] = mine.json()["items"]
    assert entry["id"] == str(row.id) and entry["university"] and entry["application_code"] == app.application_code
    assert "recorded_by" not in entry  # the student sees the interview, not the staff member who typed it
    assert [i["id"] for i in listed.json()["interviews"]] == [str(row.id)]


@pytest.mark.asyncio
async def test_an_outcome_is_accepted_only_after_the_date_and_cancelled_any_time(db_session, world):  # AC3, I3
    app = world["direct_app"]
    async with client_for(world["counselor"].email) as c:
        future = (await c.post(BASE.format(app.id), json=body())).json()["interview"]["id"]
        early = await c.patch(ONE.format(app.id, future), json={"outcome": "passed"})
        assert early.status_code == 422 and "after the interview" in early.json()["detail"]
        assert (await c.patch(ONE.format(app.id, future), json={"outcome": "cancelled"})).status_code == 200
        past = (await c.post(BASE.format(app.id), json=body(PAST, mode="in_person", location="Main campus, Room 4"))).json()["interview"]["id"]
        r = await c.patch(ONE.format(app.id, past), json={"outcome": "passed"})
        assert r.status_code == 200, r.text
        assert r.json()["interview"]["outcome_label"] == "Passed"
        moved = await c.patch(ONE.format(app.id, past), json={"scheduled_at": FUTURE.isoformat()})
        assert moved.status_code == 422  # a decided interview cannot move into the future
        cleared = await c.patch(ONE.format(app.id, past), json={"outcome": None, "scheduled_at": FUTURE.isoformat()})
        assert cleared.status_code == 200 and cleared.json()["interview"]["outcome"] is None
    assert "Interview result" in await _titles(db_session, world["direct_student"])


@pytest.mark.asyncio
async def test_validation(db_session, world):
    app = world["direct_app"]
    async with client_for(world["counselor"].email) as c:
        for bad in (
            body(mode="video"),
            body(outcome="maybe"),
            body(location="x" * 301),
            body(student_note="x" * 501),
            body() | {"scheduled_at": "2026-11-02T10:00:00"},  # no offset (I9)
            body(datetime(1999, 1, 1, tzinfo=UTC)),
        ):
            assert (await c.post(BASE.format(app.id), json=bad)).status_code == 422, bad
        assert (await c.post(BASE.format(app.id), json={"mode": "online"})).status_code == 422


@pytest.mark.asyncio
async def test_an_unchanged_save_writes_nothing_and_a_note_change_is_not_announced(db_session, world):
    app, student = world["direct_app"], world["direct_student"]
    async with client_for(world["counselor"].email) as c:
        created = (await c.post(BASE.format(app.id), json=body())).json()["interview"]
        before = len(await notices(db_session, student))
        same = await c.patch(ONE.format(app.id, created["id"]), json={"mode": "online", "scheduled_at": created["scheduled_at"]})
        assert same.status_code == 200 and same.json()["changed"] is False
        assert len(await notices(db_session, student)) == before
        note = await c.patch(ONE.format(app.id, created["id"]), json={"student_note": "Bring your transcripts."})
        assert note.status_code == 200 and note.json()["changed"] is True
        assert len(await notices(db_session, student)) == before
        moved = await c.patch(ONE.format(app.id, created["id"]), json={"scheduled_at": (FUTURE + timedelta(days=1)).isoformat()})
        assert moved.status_code == 200
    assert "Interview rescheduled" in await _titles(db_session, student)
    audits = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == str(app.id), AuditLog.action == "overseas.application.interview"))).all()
    assert len(audits) == 3 and "Bring your" not in str([a.metadata_json for a in audits])


@pytest.mark.asyncio
async def test_scope_and_roles(db_session, world):  # AC5
    app = world["direct_app"]
    async with client_for(world["counselor"].email) as c:
        interview = (await c.post(BASE.format(app.id), json=body())).json()["interview"]["id"]
    async with client_for(world["counselor2"].email) as c:
        assert (await c.get(BASE.format(app.id))).status_code == 403
        assert (await c.post(BASE.format(app.id), json=body())).status_code == 403
        assert (await c.patch(ONE.format(app.id, interview), json={"outcome": "cancelled"})).status_code == 403
    other = await mk_user(db_session, role="overseas_student")
    async with client_for(other.email) as c:
        assert (await c.get(BASE.format(app.id))).status_code == 403
        assert (await c.get(MINE)).json()["items"] == []
    async with client_for(world["direct_student"].email) as c:
        assert (await c.post(BASE.format(app.id), json=body())).status_code == 403
        assert (await c.patch(ONE.format(app.id, interview), json={"outcome": "cancelled"})).status_code == 403
    async with client_for(world["admin"].email) as c:
        assert (await c.patch(ONE.format(app.id, interview), json={"location": "Room 2"})).status_code == 200
        assert (await c.get(MINE)).status_code == 403
    async with client_for(world["counselor"].email) as c:  # an interview of another application is 404
        assert (await c.patch(ONE.format(world["app"].id, interview), json={"outcome": "cancelled"})).status_code == 404


@pytest.mark.asyncio
async def test_agency_applications_the_counselor_writes_the_agency_reads_and_is_told(db_session, world):  # CC4, CC5
    app = world["app"]
    async with client_for(world["counselor"].email) as c:
        assert (await c.post(BASE.format(app.id), json=body())).status_code == 201
    async with client_for(world["master"].email) as c:
        listed = await c.get(BASE.format(app.id))
        assert listed.status_code == 200 and len(listed.json()["interviews"]) == 1
        assert (await c.post(BASE.format(app.id), json=body())).status_code == 403
    assert "Application details updated" in await _titles(db_session, world["staff"]["user"])


@pytest.mark.asyncio
async def test_a_closed_application_refuses_writes_and_the_cap_holds(db_session, world):  # I4, I6
    app = world["direct_app"]
    async with client_for(world["counselor"].email) as c:
        for _ in range(20):
            assert (await c.post(BASE.format(app.id), json=body())).status_code == 201
        full = await c.post(BASE.format(app.id), json=body())
        assert full.status_code == 422 and "20" in full.json()["detail"]
    item = await fresh(db_session, app)
    item.status = "withdrawn"
    await db_session.commit()
    async with client_for(world["counselor"].email) as c:
        first = (await c.get(BASE.format(app.id))).json()["interviews"][0]["id"]
        assert (await c.patch(ONE.format(app.id, first), json={"outcome": "cancelled"})).status_code == 409
