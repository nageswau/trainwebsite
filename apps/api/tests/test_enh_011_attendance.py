import uuid

import pytest
from enh005_helpers import move_student_directly
from enh011_helpers import BATCHES, ENROLMENTS, SESSIONS, create_batch, enrol, login, skills_world
from sqlalchemy import func, select

from app.models import AuditLog, SchoolSkillAttendance

# ENH-011 spec §5.1: one session per batch per day (D10) and per-session attendance, upserted. AC-03, AC-06, AC-07.


async def _batch_with_two(client, w, **over):
    await login(client, w["counselor"].email)
    batch = await create_batch(client, w["a"]["school"].id, end_date="2026-12-31", **over)
    rows = await enrol(client, batch["id"], *w["a"]["students"])
    return batch, rows


async def _session(client, batch_id, day="2026-10-05", **over):
    response = await client.post(f"{BATCHES}/{batch_id}/sessions", json={"session_date": day, **over})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_add_session_and_duplicate_date_409(client, db_session):
    w = await skills_world(db_session)
    batch, _rows = await _batch_with_two(client, w)
    session = await _session(client, batch["id"], topic="  Body language ")
    assert session["session_date"] == "2026-10-05" and session["topic"] == "Body language" and session["attendance"] == []
    duplicate = await client.post(f"{BATCHES}/{batch['id']}/sessions", json={"session_date": "2026-10-05"})
    assert duplicate.status_code == 409 and "already has a session" in duplicate.json()["detail"]
    assert (await db_session.scalars(select(AuditLog).where(AuditLog.action == "school.skill_session_create", AuditLog.entity_id == session["id"]))).one()


@pytest.mark.asyncio
async def test_session_date_outside_batch_dates_422(client, db_session):
    w = await skills_world(db_session)
    batch, _rows = await _batch_with_two(client, w)
    for day in ("2026-09-30", "2027-01-01"):
        response = await client.post(f"{BATCHES}/{batch['id']}/sessions", json={"session_date": day})
        assert response.status_code == 422 and "within the batch's dates" in response.json()["detail"]


@pytest.mark.asyncio
async def test_attendance_upsert_is_idempotent_and_returns_full_set(client, db_session):
    w = await skills_world(db_session)
    batch, (r0, r1) = await _batch_with_two(client, w)
    session = await _session(client, batch["id"])
    url = f"{SESSIONS}/{session['id']}/attendance"
    first = await client.put(url, json={"records": [{"enrollment_id": r0["id"], "present": True}, {"enrollment_id": r1["id"], "present": True}]})
    assert first.status_code == 200
    second = await client.put(url, json={"records": [{"enrollment_id": r1["id"], "present": False}]})
    assert {(a["enrollment_id"], a["present"]) for a in second.json()["attendance"]} == {(r0["id"], True), (r1["id"], False)}
    again = await client.put(url, json={"records": [{"enrollment_id": r1["id"], "present": False}]})
    assert again.json() == second.json()
    count = await db_session.scalar(select(func.count()).select_from(SchoolSkillAttendance).where(SchoolSkillAttendance.session_id == session["id"]))
    assert count == 2
    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "school.skill_attendance_mark", AuditLog.entity_id == session["id"]))).all()
    assert len(audit) == 3 and audit[0].metadata_json == {"count": 2}


@pytest.mark.asyncio
async def test_detail_attendance_summary_counts_present_and_marked(client, db_session):
    w = await skills_world(db_session)
    batch, (r0, r1) = await _batch_with_two(client, w)
    s1 = await _session(client, batch["id"], "2026-10-05")
    s2 = await _session(client, batch["id"], "2026-10-12")
    await client.put(f"{SESSIONS}/{s1['id']}/attendance", json={"records": [{"enrollment_id": r0["id"], "present": True}, {"enrollment_id": r1["id"], "present": False}]})
    await client.put(f"{SESSIONS}/{s2['id']}/attendance", json={"records": [{"enrollment_id": r0["id"], "present": True}]})
    detail = (await client.get(f"{BATCHES}/{batch['id']}")).json()
    summary = {e["id"]: e["attendance"] for e in detail["enrollments"]}
    assert summary == {r0["id"]: {"present": 2, "marked": 2}, r1["id"]: {"present": 0, "marked": 1}}
    assert [s["session_date"] for s in detail["sessions"]] == ["2026-10-05", "2026-10-12"]


@pytest.mark.asyncio
async def test_attendance_for_enrolment_of_another_batch_422(client, db_session):
    w = await skills_world(db_session)
    batch, _rows = await _batch_with_two(client, w)
    other = await create_batch(client, w["a"]["school"].id, title="Other")
    [foreign] = await enrol(client, other["id"], w["a"]["students"][0])
    session = await _session(client, batch["id"])
    for enrollment_id in (foreign["id"], str(uuid.uuid4())):
        response = await client.put(f"{SESSIONS}/{session['id']}/attendance", json={"records": [{"enrollment_id": enrollment_id, "present": True}]})
        assert response.status_code == 422 and "not in this batch" in response.json()["detail"]


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["withdrawn", "certified", "frozen"])
async def test_attendance_for_withdrawn_certified_or_frozen_409(client, db_session, state):
    w = await skills_world(db_session)
    batch, (r0, _r1) = await _batch_with_two(client, w)
    session = await _session(client, batch["id"])
    if state == "frozen":
        await move_student_directly(db_session, w["a"]["students"][0], w["b"]["school"])
    else:
        assert (await client.patch(f"{ENROLMENTS}/{r0['id']}", json={"status": state})).status_code == 200
    target = r0 if state != "frozen" else next(r for r in (await client.get(f"{BATCHES}/{batch['id']}")).json()["enrollments"] if r["frozen"])
    response = await client.put(f"{SESSIONS}/{session['id']}/attendance", json={"records": [{"enrollment_id": target["id"], "present": True}]})
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_closed_batch_rejects_session_and_attendance_409(client, db_session):
    w = await skills_world(db_session)
    batch, (r0, _r1) = await _batch_with_two(client, w)
    session = await _session(client, batch["id"])
    await client.patch(f"{BATCHES}/{batch['id']}", json={"status": "closed"})
    assert (await client.post(f"{BATCHES}/{batch['id']}/sessions", json={"session_date": "2026-10-06"})).status_code == 409
    assert (await client.put(f"{SESSIONS}/{session['id']}/attendance", json={"records": [{"enrollment_id": r0["id"], "present": True}]})).status_code == 409


@pytest.mark.asyncio
async def test_session_outside_portfolio_is_404(client, db_session):
    w = await skills_world(db_session)
    batch, (r0, _r1) = await _batch_with_two(client, w)
    session = await _session(client, batch["id"])
    await login(client, w["counselor_b"].email)
    assert (await client.post(f"{BATCHES}/{batch['id']}/sessions", json={"session_date": "2026-10-06"})).status_code == 404
    assert (await client.put(f"{SESSIONS}/{session['id']}/attendance", json={"records": [{"enrollment_id": r0["id"], "present": True}]})).status_code == 404
