"""ENH-013 -- PATCH /school/students/{id}/career-goal (docs/superpowers/specs/2026-09-23-enh-013a-student-360-view-design.md §6.2)."""
import asyncio
import logging
import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.models import AuditLog, SchoolStudent
from app.schemas import CareerGoalUpdate
from tests.enh005_helpers import login, mk_school, mk_staff

GOAL = "/api/v1/school/students/{sid}/career-goal"


async def _goal_of(sid):
    """Read through a fresh session, so the answer is what is committed, not what a test session has cached."""
    async with SessionLocal() as s:
        return await s.scalar(select(SchoolStudent.career_goal).where(SchoolStudent.id == sid))


@pytest.mark.parametrize("raw, expected", [("  Technology  ", "Technology"), ("", None), ("   ", None), (None, None), ("a" * 120, "a" * 120)])
def test_career_goal_update_cleans_and_clears(raw, expected):
    assert CareerGoalUpdate(career_goal=raw).career_goal == expected


@pytest.mark.parametrize("payload", [{"career_goal": "a" * 121}, {"career_goal": "Line\nbreak"}, {"career_goal": "Bad\x00byte"}, {"career_goal": "Rev‮ersed"}, {}, {"career_goal": "x", "school_id": "y"}])
def test_career_goal_update_rejects(payload):
    with pytest.raises(ValidationError):
        CareerGoalUpdate(**payload)


def test_tab_keys_are_the_sixteen_in_display_order():
    from app.schemas import TAB_360_KEYS
    assert TAB_360_KEYS == ("overview", "personal_details", "academic_records", "attendance", "examination_results", "career_guidance", "psychometric_assessment", "skills", "foreign_languages", "english_testing", "activities", "certificates", "documents", "teacher_remarks", "parent_communication", "edusphere_programs")


@pytest.fixture(autouse=True)
def _app_loggers_enabled():
    logging.getLogger("app.student_360").disabled = False
    yield


@pytest.mark.asyncio
async def test_counselor_sets_and_clears_the_goal_with_an_audit_row(client, db_session, caplog):  # AC-07
    ctx = await mk_school(db_session, label="E13-Goal")
    kid = ctx["students"][0]
    cc = await mk_staff(db_session, ctx["school"], ctx["admin"], role="career_counselor")
    await login(client, cc.email)
    with caplog.at_level(logging.INFO, logger="app.student_360"):
        r = await client.patch(GOAL.format(sid=kid.id), json={"career_goal": "  Technology "})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["school_student_id"], body["career_goal"]) == (str(kid.id), "Technology") and body["updated_at"]
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "school.career_goal_update", AuditLog.entity_id == str(kid.id)))
    assert (audit.user_id, audit.entity_type, audit.metadata_json) == (cc.id, "school_student", {"old": None, "new": "Technology"})
    logs = [rec for rec in caplog.records if rec.name == "app.student_360" and rec.getMessage() == "career_goal_update"]
    assert logs and "Technology" not in str(logs[0].extra_fields)  # IDs only, never the free text

    await login(client, ctx["parent"].email)  # visible to every reader of the 360 view
    assert (await client.get(f"/api/v1/school/students/{kid.id}/360-view")).json()["career_goal"] == "Technology"

    await login(client, cc.email)
    assert (await client.patch(GOAL.format(sid=kid.id), json={"career_goal": ""})).json()["career_goal"] is None
    assert await _goal_of(kid.id) is None


@pytest.mark.asyncio
async def test_only_an_in_scope_career_counselor_may_write(client, db_session):  # AC-07
    a = await mk_school(db_session, label="E13-GoalA")
    b = await mk_school(db_session, label="E13-GoalB", admin=a["admin"])
    kid = a["students"][0]
    others = [a["coordinator"], a["principal"], a["teacher"], a["parent"],
              await mk_staff(db_session, a["school"], a["admin"], role="academic_team"),
              await mk_staff(db_session, a["school"], a["admin"], role="psychometric_team")]
    for who in others:
        await login(client, who.email)
        r = await client.patch(GOAL.format(sid=kid.id), json={"career_goal": "X"})
        assert (r.status_code, r.json()["detail"]) == (403, "Career Counselor role required"), who.role
    outsider = await mk_staff(db_session, b["school"], a["admin"], role="career_counselor")
    await login(client, outsider.email)
    r = await client.patch(GOAL.format(sid=kid.id), json={"career_goal": "X"})
    assert (r.status_code, r.json()["detail"]) == (403, "This student is at a school outside your own portfolio")
    assert (await client.patch(GOAL.format(sid=uuid.uuid4()), json={"career_goal": "X"})).status_code == 404
    client.cookies.clear()
    assert (await client.patch(GOAL.format(sid=kid.id), json={"career_goal": "X"})).status_code == 401
    assert await _goal_of(kid.id) is None


@pytest.mark.asyncio
async def test_invalid_payloads_are_422_and_write_nothing(client, db_session):  # AC-07
    ctx = await mk_school(db_session, label="E13-Goal422")
    kid = ctx["students"][0]
    cc = await mk_staff(db_session, ctx["school"], ctx["admin"], role="career_counselor")
    await login(client, cc.email)
    for bad in ({"career_goal": "a" * 121}, {"career_goal": "a\nb"}, {"career_goal": "x", "school_id": "y"}, {}, {"career_goal": 7}):
        assert (await client.patch(GOAL.format(sid=kid.id), json=bad)).status_code == 422, bad
    assert await _goal_of(kid.id) is None


@pytest.mark.asyncio
async def test_a_failed_audit_write_rolls_the_goal_back(client, db_session, monkeypatch):  # transaction boundary
    from app.api import student_360

    ctx = await mk_school(db_session, label="E13-GoalRollback")
    kid = ctx["students"][0]
    cc = await mk_staff(db_session, ctx["school"], ctx["admin"], role="career_counselor")
    await login(client, cc.email)
    real = student_360.AuditLog
    monkeypatch.setattr(student_360, "AuditLog", lambda **kw: real(**{**kw, "user_id": uuid.uuid4()}))  # FK violation at commit
    with pytest.raises(IntegrityError):
        await client.patch(GOAL.format(sid=kid.id), json={"career_goal": "Medicine"})
    assert await _goal_of(kid.id) is None


@pytest.mark.asyncio
async def test_a_write_racing_a_transfer_out_of_the_portfolio_is_refused(client, db_session):  # AC-08
    a = await mk_school(db_session, label="E13-RaceA")
    b = await mk_school(db_session, label="E13-RaceB", admin=a["admin"])
    kid = a["students"][0]
    cc = await mk_staff(db_session, a["school"], a["admin"], role="career_counselor")
    await login(client, cc.email)
    mover = SessionLocal()
    try:
        # Stand-in for transfer approval: hold the student's row lock (as school_transfers.py:398 does), then move the student.
        await mover.execute(select(SchoolStudent).where(SchoolStudent.id == kid.id).with_for_update())
        pending = asyncio.create_task(client.patch(GOAL.format(sid=kid.id), json={"career_goal": "Law"}))
        await asyncio.sleep(0.5)  # the PATCH has passed its first scope check and is now queued on the row lock
        assert not pending.done()
        await mover.execute(update(SchoolStudent).where(SchoolStudent.id == kid.id).values(school_id=b["school"].id))
        await mover.commit()
    finally:
        await mover.close()
    r = await pending
    assert (r.status_code, r.json()["detail"]) == (403, "This student is at a school outside your own portfolio")
    assert await _goal_of(kid.id) is None
