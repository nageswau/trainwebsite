"""ENH-015 -- GET /school/students/{id}/progress-report (spec §5.2, §6.2, §8; AC04-AC08, AC12)."""

import logging
import uuid
from datetime import UTC, datetime

import pytest
from enh016_helpers import login, make_school, make_student
from pdf_text import pdf_text
from sqlalchemy import func, select

from app.api import school_reports
from app.models import AuditLog, SchoolAcademicResult, SchoolParentLink, SchoolPsychometricRecord

URL = "/api/v1/school/students/{sid}/progress-report"
REPORT_URL = "https://files.example/secret-psychometric-report.pdf"


@pytest.fixture(autouse=True)
def _app_loggers_enabled():
    logging.getLogger("app.school_reports").disabled = False
    yield


async def _world(db) -> dict:
    """School A: `kid` (linked to A's parent) with a published and a draft result and a completed psychometric record
    carrying a report file; `sibling` at the same school, not linked. School B: `foreign`."""
    ctx = await make_school(db, name="Progress School A")
    other = await make_school(db, name="Progress School B")
    kid = await make_student(db, ctx, name="Progress Kid Asha", grade_level=9)
    sibling = await make_student(db, ctx, name="Unlinked Kid Ravi", grade_level=9)
    foreign = await make_student(db, other, name="Foreign Kid Meera", grade_level=9)
    acad = ctx["academic_team"].id
    db.add_all(
        [
            SchoolParentLink(parent_user_id=ctx["school_parent"].id, school_student_id=kid.id, linked_by_user_id=ctx["school_coordinator"].id),
            SchoolAcademicResult(
                school_student_id=kid.id,
                academic_year="2026-27",
                term="Term 1",
                subject="Physics",
                max_marks=50,
                marks_obtained=45,
                status="published",
                uploaded_by_user_id=acad,
                published_at=datetime.now(UTC),
            ),
            SchoolAcademicResult(school_student_id=kid.id, academic_year="2026-27", term="Term 1", subject="Chemistry", max_marks=50, marks_obtained=10, status="draft", uploaded_by_user_id=acad),
            SchoolPsychometricRecord(
                school_student_id=kid.id, psychometric_team_user_id=ctx["psychometric_team"].id, assessment_type="Aptitude", status="completed", report_url=REPORT_URL, strengths=["Logic"]
            ),
        ]
    )
    await db.commit()
    return {"ctx": ctx, "other": other, "kid": kid, "sibling": sibling, "foreign": foreign}


async def _audit_rows(db, student_id) -> list[AuditLog]:
    return list((await db.scalars(select(AuditLog).where(AuditLog.action == "school.progress_report_download", AuditLog.entity_id == str(student_id)))).all())


@pytest.mark.asyncio
async def test_parent_downloads_their_own_childs_report(client, db_session):  # AC04, AC05, AC07
    w = await _world(db_session)
    await login(client, w["ctx"]["school_parent"])
    response = await client.get(URL.format(sid=w["kid"].id))
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == 'attachment; filename="progress-report.pdf"'
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-security-policy"] == "default-src 'none'; sandbox"
    text = pdf_text(response.content)
    assert "Progress Kid Asha" in text
    assert "Physics" in text
    assert "Aptitude" in text and "Logic" in text  # ENH-027 result fields the parent already sees on screen (D6)


@pytest.mark.asyncio
async def test_report_never_contains_drafts_the_report_file_or_another_child(client, db_session):  # AC05
    w = await _world(db_session)
    await login(client, w["ctx"]["school_parent"])
    response = await client.get(URL.format(sid=w["kid"].id))
    text = pdf_text(response.content)
    assert "Chemistry" not in text
    assert "secret-psychometric-report" not in text and b"secret-psychometric-report" not in response.content
    assert "Unlinked Kid Ravi" not in text and "Foreign Kid Meera" not in text


@pytest.mark.asyncio
async def test_parent_cannot_download_an_unlinked_child_at_the_same_school(client, db_session):  # AC04
    w = await _world(db_session)
    await login(client, w["ctx"]["school_parent"])
    response = await client.get(URL.format(sid=w["sibling"].id))
    assert response.status_code == 403
    assert response.json()["detail"] == "This student is not linked to your account"
    assert await _audit_rows(db_session, w["sibling"].id) == []


@pytest.mark.asyncio
async def test_parent_cannot_download_a_child_at_another_school(client, db_session):  # AC04
    w = await _world(db_session)
    await login(client, w["ctx"]["school_parent"])
    assert (await client.get(URL.format(sid=w["foreign"].id))).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["school_coordinator", "school_principal"])
async def test_coordinator_and_principal_download_own_school_students_only(client, db_session, role):  # AC04
    w = await _world(db_session)
    await login(client, w["ctx"][role])
    own = await client.get(URL.format(sid=w["sibling"].id))
    assert own.status_code == 200
    assert "Unlinked Kid Ravi" in pdf_text(own.content)
    other = await client.get(URL.format(sid=w["foreign"].id))
    assert other.status_code == 403
    assert other.json()["detail"] == "This student is at a different institution"


@pytest.mark.asyncio
async def test_an_unknown_student_is_404(client, db_session):  # AC04
    w = await _world(db_session)
    await login(client, w["ctx"]["school_coordinator"])
    response = await client.get(URL.format(sid=uuid.uuid4()))
    assert response.status_code == 404
    assert response.json()["detail"] == "Student not found"


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["school_teacher", "academic_team", "career_counselor", "psychometric_team", "it_admin", "overseas_admin", "super_admin"])
async def test_every_other_role_is_refused_before_the_id_is_checked(client, db_session, role):  # AC04
    w = await _world(db_session)
    await login(client, w["ctx"][role])
    for sid in (w["kid"].id, "not-a-uuid"):
        response = await client.get(URL.format(sid=sid))
        assert response.status_code == 403, (sid, response.text)
        assert response.json()["detail"] == "Parent, School Coordinator or Principal role required"
    assert await _audit_rows(db_session, w["kid"].id) == []


@pytest.mark.asyncio
async def test_a_malformed_id_from_an_allowed_role_is_422(client, db_session):
    w = await _world(db_session)
    await login(client, w["ctx"]["school_parent"])
    assert (await client.get(URL.format(sid="not-a-uuid"))).status_code == 422


@pytest.mark.asyncio
async def test_authentication_is_required(client, db_session):
    assert (await client.get(URL.format(sid=uuid.uuid4()))).status_code == 401


@pytest.mark.asyncio
async def test_each_download_writes_one_audit_row_with_the_role_only(client, db_session):  # AC06
    w = await _world(db_session)
    parent = w["ctx"]["school_parent"]
    await login(client, parent)
    assert (await client.get(URL.format(sid=w["kid"].id))).status_code == 200
    assert (await client.get(URL.format(sid=w["kid"].id))).status_code == 200
    rows = await _audit_rows(db_session, w["kid"].id)
    assert len(rows) == 2
    assert {(r.user_id, r.entity_type, r.outcome) for r in rows} == {(parent.id, "school_student", "recorded")}
    assert all(r.metadata_json == {"role": "school_parent"} for r in rows)


def _boom(*args, **kwargs):
    raise RuntimeError("simulated audit-log write failure")


@pytest.mark.asyncio
async def test_no_pdf_leaves_when_the_audit_write_fails(client, db_session, monkeypatch):  # AC06: fail closed
    w = await _world(db_session)
    await login(client, w["ctx"]["school_parent"])
    monkeypatch.setattr(school_reports, "AuditLog", _boom)
    # ASGITransport re-raises an unhandled route exception instead of returning a 500 -- either way no PDF is returned.
    with pytest.raises(RuntimeError, match="simulated audit-log write failure"):
        await client.get(URL.format(sid=w["kid"].id))
    assert await _audit_rows(db_session, w["kid"].id) == []


@pytest.mark.asyncio
async def test_a_render_failure_is_a_generic_500_with_no_audit_row(client, db_session, monkeypatch, caplog):
    w = await _world(db_session)
    await login(client, w["ctx"]["school_parent"])

    def broken(*args, **kwargs):
        raise ValueError("Progress Kid Asha broke the layout")

    monkeypatch.setattr(school_reports, "render_progress_report", broken)
    with caplog.at_level(logging.INFO, logger="app.school_reports"):
        response = await client.get(URL.format(sid=w["kid"].id))
    assert response.status_code == 500
    assert response.json() == {"detail": "Could not generate the report; please try again"}
    assert await _audit_rows(db_session, w["kid"].id) == []
    failures = [r for r in caplog.records if r.name == "app.school_reports" and r.getMessage() == "school_report_failed"]
    assert len(failures) == 1
    assert failures[0].extra_fields["error_type"] == "ValueError"
    assert "Asha" not in str(failures[0].extra_fields)


@pytest.mark.asyncio
async def test_each_download_logs_ids_only(client, db_session, caplog):  # AC12
    w = await _world(db_session)
    await login(client, w["ctx"]["school_parent"])
    with caplog.at_level(logging.INFO, logger="app.school_reports"):
        assert (await client.get(URL.format(sid=w["kid"].id))).status_code == 200
    records = [r for r in caplog.records if r.name == "app.school_reports" and r.getMessage() == "school_report_generated"]
    assert len(records) == 1
    fields = records[0].extra_fields
    assert set(fields) == {"actor_id", "role", "report", "school_student_id", "bytes", "ms"}
    assert fields["report"] == "progress_report"
    assert fields["school_student_id"] == str(w["kid"].id)
    assert "Asha" not in str(fields)


@pytest.mark.asyncio
async def test_existing_overview_is_unchanged_by_the_report(client, db_session):  # AC11: the PDF reads, never writes
    w = await _world(db_session)
    await login(client, w["ctx"]["school_parent"])
    before = (await client.get(f"/api/v1/school/students/{w['kid'].id}/overview")).json()
    assert (await client.get(URL.format(sid=w["kid"].id))).status_code == 200
    after = (await client.get(f"/api/v1/school/students/{w['kid'].id}/overview")).json()
    assert before == after
    assert "report_url" not in str(before["psychometric"])
    count = await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == str(w["kid"].id)))
    assert count == 1
