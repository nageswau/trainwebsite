"""ENH-015 -- GET /school/reports/school-summary (spec §5.1, §6.1; AC01-AC03, AC07, AC09, AC12)."""

import logging
from datetime import date

import pytest
from enh016_helpers import login, make_school, make_student, make_university
from pdf_text import pdf_text
from sqlalchemy import event

from app.core.database import engine
from app.models import OverseasApplication, SchoolCareerRecord, SchoolPsychometricRecord, SchoolSkillBatch, SchoolSkillEnrollment

URL = "/api/v1/school/reports/school-summary"


@pytest.fixture(autouse=True)
def _app_loggers_enabled():
    """Same guard as test_enh_013: an in-process Alembic run earlier in the session disables existing `app.*` loggers."""
    logging.getLogger("app.school_reports").disabled = False
    yield


async def _seed(db, ctx) -> dict:
    """s1 (Grade 9): guidance + counselling + completed psychometric + skills batch. s2 (Grade 9): psychometric assigned only.
    s3 (no grade): an overseas application."""
    s1 = await make_student(db, ctx, name="Summary Kid One", grade_level=9)
    s2 = await make_student(db, ctx, name="Summary Kid Two", grade_level=9)
    s3 = await make_student(db, ctx, name="Summary Kid Three")
    cc, psych = ctx["career_counselor"].id, ctx["psychometric_team"].id
    db.add_all(
        [
            SchoolCareerRecord(school_student_id=s1.id, career_counselor_user_id=cc, record_type="guidance_session", notes="n"),
            SchoolCareerRecord(school_student_id=s1.id, career_counselor_user_id=cc, record_type="counselling_note", notes="n"),
            SchoolPsychometricRecord(school_student_id=s1.id, psychometric_team_user_id=psych, assessment_type="A", status="completed"),
            SchoolPsychometricRecord(school_student_id=s2.id, psychometric_team_user_id=psych, assessment_type="A"),
        ]
    )
    batch = SchoolSkillBatch(school_id=ctx["school"].id, module_type="soft_skills", title="Soft", start_date=date(2026, 1, 1), created_by_user_id=cc)
    db.add(batch)
    await db.flush()
    db.add(SchoolSkillEnrollment(batch_id=batch.id, school_student_id=s1.id, enrolled_by_user_id=cc))
    university = await make_university(db)
    db.add(OverseasApplication(student_id=None, school_student_id=s3.id, university_id=university.id, intake="Fall 2027", status="applied"))
    await db.commit()
    return {"s1": s1, "s2": s2, "s3": s3}


def _kpi(text: str, label: str, value: int) -> bool:
    return f"{label}\n{value}\n" in text + "\n"


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["school_coordinator", "school_principal"])
async def test_coordinator_and_principal_download_their_schools_summary(client, db_session, role):  # AC01, AC02, AC07
    ctx = await make_school(db_session, name="Summary Test School")
    await _seed(db_session, ctx)
    await login(client, ctx[role])
    response = await client.get(URL)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == 'attachment; filename="school-report.pdf"'
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-security-policy"] == "default-src 'none'; sandbox"
    assert response.content.startswith(b"%PDF-")
    text = pdf_text(response.content)
    assert "Summary Test School" in text
    # The dashboard KPI tiles' own wording (GET /school/dashboard), which count the same students -- so a figure in the PDF
    # reads the same as the tile it matches, not like the Reports panel's broader "Career guidance" (any career record).
    for label, value in [
        ("Total Students", 3),
        ("Career Guidance Completed", 1),
        ("Psychometric Tests Completed", 1),
        ("Individual Counselling Completed", 1),
        ("Students in Skills Programs", 1),
        ("Students in Global Education Pathway", 1),
    ]:
        assert _kpi(text, label, value), (label, value)


@pytest.mark.asyncio
async def test_management_figures_equal_the_dashboard_kpis_of_the_same_name(client, db_session):
    ctx = await make_school(db_session)
    await _seed(db_session, ctx)
    await login(client, ctx["school_coordinator"])
    kpis = {k["label"]: k["value"] for k in (await client.get("/api/v1/school/dashboard")).json()["school_crm_kpis"]}
    text = pdf_text((await client.get(URL)).content)
    for label in ("Total Students", "Career Guidance Completed", "Psychometric Tests Completed", "Individual Counselling Completed", "Students in Global Education Pathway"):
        assert _kpi(text, label, kpis[label]), (label, kpis[label])


@pytest.mark.asyncio
async def test_grade_table_matches_the_grade_performance_endpoint(client, db_session):  # AC01
    ctx = await make_school(db_session)
    await _seed(db_session, ctx)
    await login(client, ctx["school_coordinator"])
    expected = (await client.get("/api/v1/school/analytics/grade-performance")).json()
    text = pdf_text((await client.get(URL)).content)
    assert expected["grades"] == ["9", "unspecified"]
    assert "Grade 9" in text and "No grade" in text  # the on-screen labels (SchoolGradePerformance.tsx), not the keys
    for metric in expected["metrics"]:
        assert metric["label"] in text
        for grade in expected["grades"]:
            cell = metric["cells"][grade]
            pct = "—" if cell["pct"] is None else f"{cell['pct']:g}%"
            assert f"{cell['count']} ({pct})" in text, (metric["key"], grade)


@pytest.mark.asyncio
async def test_another_schools_students_are_never_counted(client, db_session):  # AC03
    mine = await make_school(db_session)
    theirs = await make_school(db_session, name="Other Summary School")
    await _seed(db_session, theirs)
    await make_student(db_session, mine, grade_level=10)
    await db_session.commit()
    await login(client, mine["school_coordinator"])
    text = pdf_text((await client.get(URL)).content)
    assert "Other Summary School" not in text
    assert _kpi(text, "Total Students", 1)
    assert _kpi(text, "Career Guidance Completed", 0)
    assert "Grade 9" not in text


@pytest.mark.asyncio
async def test_an_empty_school_gets_a_report_that_says_so(client, db_session):
    ctx = await make_school(db_session)
    await db_session.commit()
    await login(client, ctx["school_coordinator"])
    response = await client.get(URL)
    assert response.status_code == 200
    text = pdf_text(response.content)
    assert "No students on the roster yet." in text
    assert _kpi(text, "Total Students", 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["school_teacher", "school_parent", "academic_team", "career_counselor", "psychometric_team", "it_admin", "overseas_admin", "super_admin"])
async def test_every_other_role_is_refused(client, db_session, role):  # AC02
    ctx = await make_school(db_session)
    await db_session.commit()
    await login(client, ctx[role])
    response = await client.get(URL)
    assert response.status_code == 403
    assert response.json()["detail"] == "School Coordinator or Principal role required"


@pytest.mark.asyncio
async def test_a_school_account_without_a_school_is_refused(client, db_session):  # AC02
    ctx = await make_school(db_session)
    ctx["school_coordinator"].profile = {}
    await db_session.commit()
    await login(client, ctx["school_coordinator"])
    response = await client.get(URL)
    assert response.status_code == 403
    assert response.json()["detail"] == "This account is not linked to a school"


@pytest.mark.asyncio
async def test_authentication_is_required(client):  # AC02
    assert (await client.get(URL)).status_code == 401


@pytest.mark.asyncio
async def test_query_count_does_not_grow_with_students(client, db_session):  # AC09
    small = await make_school(db_session)
    large = await make_school(db_session)
    await make_student(db_session, small, grade_level=9)
    for i in range(15):
        await make_student(db_session, large, grade_level=8 + i % 5)
    await db_session.commit()

    async def statements(ctx) -> int:
        await login(client, ctx["school_coordinator"])
        seen: list[str] = []
        listener = lambda conn, cursor, statement, *a: seen.append(statement)  # noqa: E731
        event.listen(engine.sync_engine, "before_cursor_execute", listener)
        try:
            assert (await client.get(URL)).status_code == 200
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", listener)
        return len(seen)

    assert await statements(small) == await statements(large)


@pytest.mark.asyncio
async def test_each_download_logs_ids_and_counts_only(client, db_session, caplog):  # AC12
    ctx = await make_school(db_session)
    await _seed(db_session, ctx)
    await login(client, ctx["school_coordinator"])
    with caplog.at_level(logging.INFO, logger="app.school_reports"):
        assert (await client.get(URL)).status_code == 200
    records = [r for r in caplog.records if r.name == "app.school_reports" and r.getMessage() == "school_report_generated"]
    assert len(records) == 1
    fields = records[0].extra_fields
    assert set(fields) == {"actor_id", "role", "report", "school_id", "student_count", "bytes", "ms"}
    assert fields["actor_id"] == str(ctx["school_coordinator"].id)
    assert fields["report"] == "school_summary"
    assert fields["school_id"] == str(ctx["school"].id)
    assert fields["student_count"] == "3"
    assert "Summary Kid" not in str(fields)


def test_openapi_documents_a_pdf_response():  # API contract
    from app.main import app

    op = app.openapi()["paths"][URL]["get"]
    assert "application/pdf" in op["responses"]["200"]["content"]
