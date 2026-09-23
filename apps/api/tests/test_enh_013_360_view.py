"""ENH-013 -- GET /school/students/{id}/360-view (docs/superpowers/specs/2026-09-23-enh-013a-student-360-view-design.md §6.1,
§6.3; AC-01..AC-06, AC-09)."""
import logging
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import event

from app.core.database import engine
from app.models import PortfolioEntry, SchoolActivity, SchoolActivityAttendance, SchoolCareerRecord, SchoolLanguageRecord, SchoolPsychometricRecord, SchoolTestPrepRecord
from app.schemas import TAB_360_KEYS
from tests.enh005_helpers import login, mk_result, mk_school, mk_staff, mk_user

URL = "/api/v1/school/students/{sid}/360-view"


@pytest.fixture(autouse=True)
def _app_loggers_enabled():
    """Same guard as test_enh_003: an in-process Alembic run earlier in the session disables existing `app.*` loggers."""
    logging.getLogger("app.student_360").disabled = False
    yield


async def _fill(db, ctx, n: int = 1):
    """n rows in every source for ctx's first student (published results carry teacher remarks)."""
    kid, coord = ctx["students"][0], ctx["coordinator"]
    staff = await mk_staff(db, ctx["school"], ctx["admin"], role="academic_team")
    for i in range(n):
        db.add(SchoolCareerRecord(school_student_id=kid.id, career_counselor_user_id=coord.id, record_type="guidance_session", notes=f"note {i}"))
        db.add(SchoolPsychometricRecord(school_student_id=kid.id, psychometric_team_user_id=coord.id, assessment_type=f"Aptitude {i}", report_url="/local-files/uploads/r.pdf", status="completed"))
        db.add(SchoolTestPrepRecord(school_student_id=kid.id, academic_team_user_id=staff.id, test_type="ielts"))
        db.add(SchoolLanguageRecord(school_student_id=kid.id, academic_team_user_id=staff.id, language="French"))
        activity = SchoolActivity(school_id=ctx["school"].id, title=f"Seminar {i}", scheduled_at=datetime.now(UTC), created_by_user_id=coord.id)
        db.add(activity)
        await db.flush()
        db.add(SchoolActivityAttendance(activity_id=activity.id, school_student_id=kid.id, present=True, marked_by_user_id=coord.id))
        for section in ("award", "certification", "skill", "project"):
            db.add(PortfolioEntry(school_student_id=kid.id, section=section, title=f"{section} {i}", created_by_user_id=coord.id, updated_by_user_id=coord.id))
        await db.commit()
        result = await mk_result(db, kid, staff, status="published", subject=f"Subject {i}")
        result.teacher_remarks = f"Remark {i}"
        await db.commit()
    return kid


@pytest.mark.asyncio
async def test_coordinator_sees_all_sixteen_tabs_populated(client, db_session):  # AC-01
    ctx = await mk_school(db_session, label="E13-Full")
    kid = await _fill(db_session, ctx)
    await login(client, ctx["coordinator"].email)
    r = await client.get(URL.format(sid=kid.id))
    assert r.status_code == 200, r.text
    body = r.json()
    assert tuple(body["tabs"]) == TAB_360_KEYS
    statuses = {k: t["status"] for k, t in body["tabs"].items()}
    assert statuses["parent_communication"] == "empty"
    assert statuses["academic_records"] == "empty"  # has data only after a promotion (AC-01 wording)
    assert all(s == "has_data" for k, s in statuses.items() if k not in {"parent_communication", "academic_records"}), statuses
    assert body["student"]["student_code"] == kid.student_code
    assert body["student"]["assigned_teacher_name"] == ctx["teacher"].full_name
    assert body["can_edit_career_goal"] is False
    assert body["tabs"]["parent_communication"]["not_tracked"] == ["A parent communication log is not tracked yet (ENH-013b / ENH-014)."]


@pytest.mark.asyncio
async def test_new_enrolment_renders_every_tab_empty_not_an_error(client, db_session):  # AC-04
    ctx = await mk_school(db_session, label="E13-Empty")
    kid = ctx["students"][0]
    for who in ("coordinator", "principal", "teacher", "parent"):
        await login(client, ctx[who].email)
        r = await client.get(URL.format(sid=kid.id))
        assert r.status_code == 200, (who, r.text)
        for key, tab in r.json()["tabs"].items():
            expected = "has_data" if key == "personal_details" else "empty"
            assert tab["status"] == expected, (who, key, tab)


@pytest.mark.asyncio
async def test_teacher_outside_assignment_is_rejected(client, db_session):  # AC-02
    ctx = await mk_school(db_session, label="E13-Teach", students=2)
    await login(client, ctx["teacher"].email)
    r = await client.get(URL.format(sid=ctx["students"][1].id))
    assert (r.status_code, r.json()["detail"]) == (403, "This student is not assigned to you")


@pytest.mark.asyncio
async def test_scope_matrix_rejections(client, db_session):  # AC-03
    a = await mk_school(db_session, label="E13-ScopeA", students=2)
    b = await mk_school(db_session, label="E13-ScopeB", admin=a["admin"])
    kid, sibling = a["students"]
    cases = [
        (a["parent"], sibling.id, 403, "This student is not linked to your account"),
        (b["coordinator"], kid.id, 403, "This student is at a different institution"),
        (b["principal"], kid.id, 403, "This student is at a different institution"),
        (await mk_staff(db_session, b["school"], a["admin"], role="psychometric_team"), kid.id, 403, "This student is at a school outside your own portfolio"),
        (await mk_user(db_session, role="overseas_admin", name="Admin"), kid.id, 403, "School role required"),
        (a["coordinator"], uuid.uuid4(), 404, "Student not found"),
    ]
    await db_session.commit()  # mk_user only flushes
    for who, sid, status, detail in cases:
        await login(client, who.email)
        r = await client.get(URL.format(sid=sid))
        assert (r.status_code, r.json()["detail"]) == (status, detail), who.role
    client.cookies.clear()
    assert (await client.get(URL.format(sid=kid.id))).status_code == 401
    await login(client, a["coordinator"].email)
    assert (await client.get("/api/v1/school/students/not-a-uuid/360-view")).status_code == 422


@pytest.mark.asyncio
async def test_unpublished_results_never_appear(client, db_session):  # AC-06
    ctx = await mk_school(db_session, label="E13-Draft")
    kid = ctx["students"][0]
    staff = await mk_staff(db_session, ctx["school"], ctx["admin"])
    await mk_result(db_session, kid, staff, status="draft", subject="Hidden draft")
    await mk_result(db_session, kid, staff, status="verified", subject="Hidden verified")
    for who in (ctx["coordinator"], staff):
        await login(client, who.email)
        r = await client.get(URL.format(sid=kid.id))
        assert r.status_code == 200
        assert "Hidden" not in r.text


@pytest.mark.asyncio
async def test_query_count_does_not_grow_with_rows(client, db_session):  # AC-09
    one = await mk_school(db_session, label="E13-Q1")
    many = await mk_school(db_session, label="E13-Q20", admin=one["admin"])
    kid1 = await _fill(db_session, one, 1)
    kid20 = await _fill(db_session, many, 20)

    async def statements(ctx, kid) -> int:
        await login(client, ctx["coordinator"].email)
        seen = []
        listener = lambda conn, cursor, statement, *a: seen.append(statement)  # noqa: E731
        event.listen(engine.sync_engine, "before_cursor_execute", listener)
        try:
            assert (await client.get(URL.format(sid=kid.id))).status_code == 200
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", listener)
        return len(seen)

    assert await statements(one, kid1) == await statements(many, kid20)


@pytest.mark.asyncio
async def test_each_read_logs_ids_only(client, db_session, caplog):
    ctx = await mk_school(db_session, label="E13-Log")
    kid = ctx["students"][0]
    await login(client, ctx["coordinator"].email)
    with caplog.at_level(logging.INFO, logger="app.student_360"):
        assert (await client.get(URL.format(sid=kid.id))).status_code == 200
    records = [r for r in caplog.records if r.name == "app.student_360" and r.getMessage() == "student_360_view"]
    assert len(records) == 1
    assert records[0].extra_fields == {"actor_id": str(ctx["coordinator"].id), "role": "school_coordinator", "student_id": str(kid.id)}
