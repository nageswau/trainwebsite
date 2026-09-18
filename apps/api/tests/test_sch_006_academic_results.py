"""SCH-006 -- Academic Results module (Draft -> Verified -> Published).

Academic Team uploads a result (subject/term/marks) for assigned school-affiliated
students; a result is not visible to Parent/Student/Teacher/Coordinator until it passes
Draft -> Verified -> Published. `DEC-ROLE-007`: the uploader may never also verify or
publish their own entry -- a portfolio needs at least two Academic Team members. Net-new.
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.identifiers import unique_student_code
from app.core.security import hash_password
from app.models import AuditLog, School, SchoolAcademicResult, SchoolStaffAssignment, SchoolStudent, User, UserRoleAssignment

PASSWORD = "Sup3r-Secret-Pass!"


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD, "division": "overseas"})
    assert response.status_code == 200


async def _create_school_with_coordinator(db_session) -> dict:
    admin = User(email=f"sch006-admin-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Overseas Admin", role="overseas_admin", division="overseas", active=True)
    db_session.add(admin)
    await db_session.flush()
    school = School(name=f"SCH-006 Test School {uuid.uuid4().hex[:6]}", created_by_user_id=admin.id)
    db_session.add(school)
    await db_session.flush()
    coordinator = User(email=f"sch006-coord-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Coordinator", role="school_coordinator", division="overseas", active=True, profile={"school_id": str(school.id)})
    db_session.add(coordinator)
    await db_session.flush()
    db_session.add(UserRoleAssignment(user_id=coordinator.id, division="overseas", role="school_coordinator", is_active=True, assigned_by_user_id=admin.id, approval_status="approved"))
    student = SchoolStudent(school_id=school.id, student_code=await unique_student_code(db_session, SchoolStudent.student_code), full_name="Test Student", created_by_user_id=coordinator.id)
    db_session.add(student)
    await db_session.flush()
    await db_session.commit()
    return {"admin": admin, "school": school, "coordinator": coordinator, "student": student}


async def _add_academic_team_member(db_session, admin, school) -> User:
    member = User(email=f"sch006-academic-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Academic Team Member", role="academic_team", division="overseas", active=True, profile={})
    db_session.add(member)
    await db_session.flush()
    db_session.add(UserRoleAssignment(user_id=member.id, division="overseas", role="academic_team", is_active=True, assigned_by_user_id=admin.id, approval_status="approved"))
    db_session.add(SchoolStaffAssignment(user_id=member.id, school_id=school.id, role="academic_team", assigned_by_user_id=admin.id))
    await db_session.commit()
    return member


@pytest.mark.asyncio
async def test_teacher_remarks_column_round_trips_on_the_model(db_session):
    """ENH-002: SchoolAcademicResult must accept and persist teacher_remarks."""
    admin = User(email=f"enh002-admin-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Admin", role="overseas_admin", division="overseas", active=True)
    db_session.add(admin)
    await db_session.flush()
    school = School(name=f"ENH-002 Test School {uuid.uuid4().hex[:6]}", created_by_user_id=admin.id)
    db_session.add(school)
    await db_session.flush()
    student = SchoolStudent(school_id=school.id, student_code=await unique_student_code(db_session, SchoolStudent.student_code), full_name="Remarks Student", created_by_user_id=admin.id)
    db_session.add(student)
    await db_session.flush()
    result = SchoolAcademicResult(
        school_student_id=student.id, academic_year="2026", term="Term 1", subject="Mathematics",
        max_marks=100, marks_obtained=90, status="draft", uploaded_by_user_id=admin.id,
        teacher_remarks="Strong grasp of algebra.",
    )
    db_session.add(result)
    await db_session.commit()
    await db_session.refresh(result)
    assert result.teacher_remarks == "Strong grasp of algebra."


@pytest.mark.asyncio
async def test_teacher_remarks_can_be_set_on_upload(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    uploader = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, uploader.email)
    response = await client.post("/api/v1/school/academic-team/results", json={
        "school_student_id": str(ctx["student"].id), "academic_year": "2026", "term": "Term 1",
        "subject": "Mathematics", "max_marks": 100, "marks_obtained": 85,
        "teacher_remarks": "Good improvement this term.",
    })
    assert response.status_code == 201, response.text
    assert response.json()["teacher_remarks"] == "Good improvement this term."


@pytest.mark.asyncio
async def test_teacher_remarks_is_optional_on_upload(client, db_session):
    """Backward compatibility: omitting teacher_remarks must keep working exactly as before."""
    ctx = await _create_school_with_coordinator(db_session)
    uploader = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, uploader.email)
    response = await client.post("/api/v1/school/academic-team/results", json={
        "school_student_id": str(ctx["student"].id), "academic_year": "2026", "term": "Term 1",
        "subject": "Mathematics", "max_marks": 100, "marks_obtained": 85,
    })
    assert response.status_code == 201, response.text
    assert response.json()["teacher_remarks"] is None


@pytest.mark.asyncio
async def test_academic_team_uploads_a_result_as_draft(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    uploader = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, uploader.email)
    response = await client.post("/api/v1/school/academic-team/results", json={"school_student_id": str(ctx["student"].id), "academic_year": "2026", "term": "Term 1", "subject": "Mathematics", "max_marks": 100, "marks_obtained": 85})
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "draft"
    assert data["percentage"] == 85.0


@pytest.mark.asyncio
async def test_academic_team_outside_the_students_portfolio_cannot_upload(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    other_school = ctx["school"]  # will not be assigned to the member below
    unassigned_member = User(email=f"sch006-noaccess-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="No Portfolio", role="academic_team", division="overseas", active=True, profile={})
    db_session.add(unassigned_member)
    await db_session.flush()
    db_session.add(UserRoleAssignment(user_id=unassigned_member.id, division="overseas", role="academic_team", is_active=True, assigned_by_user_id=ctx["admin"].id, approval_status="approved"))
    await db_session.commit()
    await _login(client, unassigned_member.email)
    response = await client.post("/api/v1/school/academic-team/results", json={"school_student_id": str(ctx["student"].id), "academic_year": "2026", "term": "Term 1", "subject": "Mathematics", "max_marks": 100, "marks_obtained": 85})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_the_uploader_cannot_verify_or_publish_their_own_result(client, db_session):
    """DEC-ROLE-007."""
    ctx = await _create_school_with_coordinator(db_session)
    uploader = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, uploader.email)
    created = await client.post("/api/v1/school/academic-team/results", json={"school_student_id": str(ctx["student"].id), "academic_year": "2026", "term": "Term 1", "subject": "Science", "max_marks": 50, "marks_obtained": 40})
    result_id = created.json()["id"]

    verify_attempt = await client.post(f"/api/v1/school/academic-team/results/{result_id}/verify")
    assert verify_attempt.status_code == 403
    assert "cannot verify or publish your own" in verify_attempt.json()["detail"]


@pytest.mark.asyncio
async def test_a_different_academic_team_member_verifies_then_publishes(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    uploader = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    reviewer = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, uploader.email)
    created = await client.post("/api/v1/school/academic-team/results", json={"school_student_id": str(ctx["student"].id), "academic_year": "2026", "term": "Term 1", "subject": "English", "max_marks": 100, "marks_obtained": 92})
    result_id = created.json()["id"]

    await _login(client, reviewer.email)
    verified = await client.post(f"/api/v1/school/academic-team/results/{result_id}/verify")
    assert verified.status_code == 200
    assert verified.json()["status"] == "verified"

    published = await client.post(f"/api/v1/school/academic-team/results/{result_id}/publish")
    assert published.status_code == 200
    assert published.json()["status"] == "published"

    result = await db_session.get(SchoolAcademicResult, uuid.UUID(result_id))
    assert result.verified_by_user_id == reviewer.id
    assert result.published_by_user_id == reviewer.id
    assert result.uploaded_by_user_id == uploader.id


@pytest.mark.asyncio
async def test_a_result_cannot_skip_a_stage(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    uploader = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    reviewer = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, uploader.email)
    created = await client.post("/api/v1/school/academic-team/results", json={"school_student_id": str(ctx["student"].id), "academic_year": "2026", "term": "Term 1", "subject": "History", "max_marks": 100, "marks_obtained": 70})
    result_id = created.json()["id"]

    await _login(client, reviewer.email)
    skip_attempt = await client.post(f"/api/v1/school/academic-team/results/{result_id}/publish")
    assert skip_attempt.status_code == 409


@pytest.mark.asyncio
async def test_coordinator_never_sees_a_draft_or_verified_result_even_via_direct_query(client, db_session):
    """SCH-006-AC02."""
    ctx = await _create_school_with_coordinator(db_session)
    uploader = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, uploader.email)
    await client.post("/api/v1/school/academic-team/results", json={"school_student_id": str(ctx["student"].id), "academic_year": "2026", "term": "Term 1", "subject": "Draft Subject", "max_marks": 100, "marks_obtained": 60})

    await _login(client, ctx["coordinator"].email)
    readable = await client.get("/api/v1/school/results")
    assert readable.status_code == 200
    assert readable.json() == []


@pytest.mark.asyncio
async def test_coordinator_sees_a_published_result(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    uploader = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    reviewer = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, uploader.email)
    created = await client.post("/api/v1/school/academic-team/results", json={"school_student_id": str(ctx["student"].id), "academic_year": "2026", "term": "Term 1", "subject": "Published Subject", "max_marks": 100, "marks_obtained": 75})
    result_id = created.json()["id"]
    await _login(client, reviewer.email)
    await client.post(f"/api/v1/school/academic-team/results/{result_id}/verify")
    await client.post(f"/api/v1/school/academic-team/results/{result_id}/publish")

    await _login(client, ctx["coordinator"].email)
    readable = await client.get("/api/v1/school/results")
    assert readable.status_code == 200
    assert len(readable.json()) == 1
    assert readable.json()[0]["subject"] == "Published Subject"


@pytest.mark.asyncio
async def test_non_academic_team_cannot_upload_a_result(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    await _login(client, ctx["coordinator"].email)
    response = await client.post("/api/v1/school/academic-team/results", json={"school_student_id": str(ctx["student"].id), "academic_year": "2026", "term": "Term 1", "subject": "X", "max_marks": 100, "marks_obtained": 50})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_a_draft_result_can_only_be_edited_while_still_draft(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    uploader = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    reviewer = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, uploader.email)
    created = await client.post("/api/v1/school/academic-team/results", json={"school_student_id": str(ctx["student"].id), "academic_year": "2026", "term": "Term 1", "subject": "Edit Me", "max_marks": 100, "marks_obtained": 55})
    result_id = created.json()["id"]

    edited = await client.patch(f"/api/v1/school/academic-team/results/{result_id}", json={"marks_obtained": 65})
    assert edited.status_code == 200
    assert edited.json()["marks_obtained"] == 65.0

    await _login(client, reviewer.email)
    await client.post(f"/api/v1/school/academic-team/results/{result_id}/verify")

    await _login(client, uploader.email)
    edit_after_verify = await client.patch(f"/api/v1/school/academic-team/results/{result_id}", json={"marks_obtained": 99})
    assert edit_after_verify.status_code == 409


@pytest.mark.asyncio
async def test_teacher_remarks_can_be_edited_while_draft(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    uploader = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, uploader.email)
    created = await client.post("/api/v1/school/academic-team/results", json={"school_student_id": str(ctx["student"].id), "academic_year": "2026", "term": "Term 1", "subject": "Physics", "max_marks": 100, "marks_obtained": 70})
    result_id = created.json()["id"]

    edited = await client.patch(f"/api/v1/school/academic-team/results/{result_id}", json={"teacher_remarks": "Needs more practice with vectors."})
    assert edited.status_code == 200
    assert edited.json()["teacher_remarks"] == "Needs more practice with vectors."


@pytest.mark.asyncio
async def test_teacher_remarks_cannot_be_edited_after_verify(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    uploader = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    reviewer = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, uploader.email)
    created = await client.post("/api/v1/school/academic-team/results", json={"school_student_id": str(ctx["student"].id), "academic_year": "2026", "term": "Term 1", "subject": "Physics", "max_marks": 100, "marks_obtained": 70})
    result_id = created.json()["id"]

    await _login(client, reviewer.email)
    await client.post(f"/api/v1/school/academic-team/results/{result_id}/verify")

    await _login(client, uploader.email)
    edit_after_verify = await client.patch(f"/api/v1/school/academic-team/results/{result_id}", json={"teacher_remarks": "Too late."})
    assert edit_after_verify.status_code == 409


@pytest.mark.asyncio
async def test_teacher_remarks_over_2000_chars_is_rejected_on_create(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    uploader = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, uploader.email)
    response = await client.post("/api/v1/school/academic-team/results", json={
        "school_student_id": str(ctx["student"].id), "academic_year": "2026", "term": "Term 1",
        "subject": "Mathematics", "max_marks": 100, "marks_obtained": 85,
        "teacher_remarks": "x" * 2001,
    })
    assert response.status_code == 422
    assert "teacher_remarks" in response.json()["detail"]


@pytest.mark.asyncio
async def test_teacher_remarks_at_exactly_2000_chars_is_accepted(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    uploader = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, uploader.email)
    response = await client.post("/api/v1/school/academic-team/results", json={
        "school_student_id": str(ctx["student"].id), "academic_year": "2026", "term": "Term 1",
        "subject": "Mathematics", "max_marks": 100, "marks_obtained": 85,
        "teacher_remarks": "x" * 2000,
    })
    assert response.status_code == 201, response.text


@pytest.mark.asyncio
async def test_teacher_remarks_over_2000_chars_is_rejected_on_update(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    uploader = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, uploader.email)
    created = await client.post("/api/v1/school/academic-team/results", json={"school_student_id": str(ctx["student"].id), "academic_year": "2026", "term": "Term 1", "subject": "Chemistry", "max_marks": 100, "marks_obtained": 60})
    result_id = created.json()["id"]
    edited = await client.patch(f"/api/v1/school/academic-team/results/{result_id}", json={"teacher_remarks": "x" * 2001})
    assert edited.status_code == 422


@pytest.mark.asyncio
async def test_teacher_remarks_is_not_leaked_before_publish(client, db_session):
    """SCH-006-AC02, extended to the new field: a draft/verified result's teacher_remarks
    must never reach /school/results, exactly like every other field on that result."""
    ctx = await _create_school_with_coordinator(db_session)
    uploader = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, uploader.email)
    await client.post("/api/v1/school/academic-team/results", json={"school_student_id": str(ctx["student"].id), "academic_year": "2026", "term": "Term 1", "subject": "Biology", "max_marks": 100, "marks_obtained": 88, "teacher_remarks": "Excellent lab work."})

    await _login(client, ctx["coordinator"].email)
    readable = await client.get("/api/v1/school/results")
    assert readable.status_code == 200
    assert readable.json() == []


@pytest.mark.asyncio
async def test_teacher_remarks_is_visible_once_published(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    uploader = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    reviewer = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, uploader.email)
    created = await client.post("/api/v1/school/academic-team/results", json={"school_student_id": str(ctx["student"].id), "academic_year": "2026", "term": "Term 1", "subject": "Biology", "max_marks": 100, "marks_obtained": 88, "teacher_remarks": "Excellent lab work."})
    result_id = created.json()["id"]
    await _login(client, reviewer.email)
    await client.post(f"/api/v1/school/academic-team/results/{result_id}/verify")
    await client.post(f"/api/v1/school/academic-team/results/{result_id}/publish")

    await _login(client, ctx["coordinator"].email)
    readable = await client.get("/api/v1/school/results")
    assert readable.status_code == 200
    assert readable.json()[0]["teacher_remarks"] == "Excellent lab work."


@pytest.mark.asyncio
async def test_teacher_remarks_content_is_never_written_to_the_audit_log(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    uploader = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, uploader.email)
    await client.post("/api/v1/school/academic-team/results", json={"school_student_id": str(ctx["student"].id), "academic_year": "2026", "term": "Term 1", "subject": "Biology", "max_marks": 100, "marks_obtained": 88, "teacher_remarks": "A private observation about this student."})

    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "school.result_create"))).all()
    assert rows, "expected an AuditLog row for the create action"
    for row in rows:
        assert "A private observation" not in str(row.metadata_json)


@pytest.mark.asyncio
async def test_progress_endpoint_requires_academic_team_role(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    await _login(client, ctx["coordinator"].email)
    response = await client.get("/api/v1/school/academic-team/progress")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_progress_endpoint_rejects_career_counselor_and_psychometric_team(client, db_session):
    """Anti-regression: this endpoint must use the singular academic_team check, not a
    copy-pasted multi-role tuple that would accidentally admit these two sibling roles."""
    ctx = await _create_school_with_coordinator(db_session)
    for role in ("career_counselor", "psychometric_team"):
        member = User(email=f"enh002-{role}-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Sibling Role", role=role, division="overseas", active=True, profile={})
        db_session.add(member)
        await db_session.flush()
        db_session.add(UserRoleAssignment(user_id=member.id, division="overseas", role=role, is_active=True, assigned_by_user_id=ctx["admin"].id, approval_status="approved"))
        db_session.add(SchoolStaffAssignment(user_id=member.id, school_id=ctx["school"].id, role=role, assigned_by_user_id=ctx["admin"].id))
        await db_session.commit()
        await _login(client, member.email)
        response = await client.get("/api/v1/school/academic-team/progress")
        assert response.status_code == 403, f"{role} must not access the Academic Team progress view"


@pytest.mark.asyncio
async def test_progress_endpoint_only_includes_the_callers_own_portfolio(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    member = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    other_school = School(name=f"ENH-002 Other School {uuid.uuid4().hex[:6]}", created_by_user_id=ctx["admin"].id)
    db_session.add(other_school)
    await db_session.flush()
    other_student = SchoolStudent(school_id=other_school.id, student_code=await unique_student_code(db_session, SchoolStudent.student_code), full_name="Outside Portfolio", created_by_user_id=ctx["admin"].id)
    db_session.add(other_student)
    await db_session.commit()

    await _login(client, member.email)
    response = await client.get("/api/v1/school/academic-team/progress")
    assert response.status_code == 200
    student_ids = {row["school_student_id"] for row in response.json()}
    assert str(ctx["student"].id) in student_ids
    assert str(other_student.id) not in student_ids


@pytest.mark.asyncio
async def test_progress_endpoint_returns_empty_list_for_a_member_with_no_portfolio(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    unassigned = User(email=f"enh002-noportfolio-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="No Portfolio", role="academic_team", division="overseas", active=True, profile={})
    db_session.add(unassigned)
    await db_session.flush()
    db_session.add(UserRoleAssignment(user_id=unassigned.id, division="overseas", role="academic_team", is_active=True, assigned_by_user_id=ctx["admin"].id, approval_status="approved"))
    await db_session.commit()
    await _login(client, unassigned.email)
    response = await client.get("/api/v1/school/academic-team/progress")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_progress_includes_a_student_with_zero_results(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    member = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, member.email)
    response = await client.get("/api/v1/school/academic-team/progress")
    assert response.status_code == 200
    row = next(r for r in response.json() if r["school_student_id"] == str(ctx["student"].id))
    assert row["result_count"] == 0
    assert row["average_percentage"] is None


@pytest.mark.asyncio
async def test_progress_average_reflects_mixed_max_marks_across_subjects(client, db_session):
    """Average of PERCENTAGES per subject, not sum(marks)/sum(max_marks) -- subjects can
    have different max_marks, so those two formulas diverge and only the former is correct."""
    ctx = await _create_school_with_coordinator(db_session)
    uploader = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, uploader.email)
    await client.post("/api/v1/school/academic-team/results", json={"school_student_id": str(ctx["student"].id), "academic_year": "2026", "term": "Term 1", "subject": "Mathematics", "max_marks": 100, "marks_obtained": 80})
    await client.post("/api/v1/school/academic-team/results", json={"school_student_id": str(ctx["student"].id), "academic_year": "2026", "term": "Term 1", "subject": "Art", "max_marks": 20, "marks_obtained": 10})
    # 80% and 50% -> average 65%, NOT (80+10)/(100+20)*100 = 75%.
    response = await client.get("/api/v1/school/academic-team/progress")
    row = next(r for r in response.json() if r["school_student_id"] == str(ctx["student"].id))
    assert row["result_count"] == 2
    assert row["average_percentage"] == 65.0


@pytest.mark.asyncio
async def test_progress_spans_every_school_in_a_multi_school_portfolio(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    member = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    second_school = School(name=f"ENH-002 Second School {uuid.uuid4().hex[:6]}", created_by_user_id=ctx["admin"].id)
    db_session.add(second_school)
    await db_session.flush()
    db_session.add(SchoolStaffAssignment(user_id=member.id, school_id=second_school.id, role="academic_team", assigned_by_user_id=ctx["admin"].id))
    second_student = SchoolStudent(school_id=second_school.id, student_code=await unique_student_code(db_session, SchoolStudent.student_code), full_name="Second School Student", created_by_user_id=ctx["admin"].id)
    db_session.add(second_student)
    await db_session.commit()

    await _login(client, member.email)
    response = await client.get("/api/v1/school/academic-team/progress")
    student_ids = {row["school_student_id"] for row in response.json()}
    assert str(ctx["student"].id) in student_ids
    assert str(second_student.id) in student_ids
    row = next(r for r in response.json() if r["school_student_id"] == str(second_student.id))
    assert row["school_name"] == second_school.name


@pytest.mark.asyncio
async def test_a_peer_cannot_edit_another_members_draft(client, db_session):
    """Codex finding #1: without an uploader check on PATCH, member B could rewrite member
    A's draft and then verify/publish B's own rewritten content (B is not the recorded
    uploader), defeating DEC-ROLE-007's separation of duties."""
    ctx = await _create_school_with_coordinator(db_session)
    uploader = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    peer = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, uploader.email)
    created = await client.post("/api/v1/school/academic-team/results", json={"school_student_id": str(ctx["student"].id), "academic_year": "2026", "term": "Term 1", "subject": "Geography", "max_marks": 100, "marks_obtained": 40, "teacher_remarks": "Original remark."})
    result_id = created.json()["id"]

    await _login(client, peer.email)
    hijack = await client.patch(f"/api/v1/school/academic-team/results/{result_id}", json={"marks_obtained": 99, "teacher_remarks": "Rewritten by a peer."})
    assert hijack.status_code == 403

    row = await db_session.get(SchoolAcademicResult, uuid.UUID(result_id))
    await db_session.refresh(row)
    assert float(row.marks_obtained) == 40.0
    assert row.teacher_remarks == "Original remark."


@pytest.mark.asyncio
async def test_two_concurrent_verifications_record_exactly_one_transition(client, db_session):
    """Codex finding #2: verify does read -> check status -> mutate -> commit with no row
    lock, so two reviewers racing on the same draft could both 'win' and write two
    draft -> verified history rows. A race is probabilistic, so several results are raced
    per run to make an unlocked implementation fail reliably."""
    import asyncio

    from httpx import ASGITransport, AsyncClient

    from app.main import app
    from app.models import SchoolResultStatusHistory

    ctx = await _create_school_with_coordinator(db_session)
    uploader = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    reviewer_b = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    reviewer_c = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, uploader.email)
    result_ids = []
    for n in range(6):
        created = await client.post("/api/v1/school/academic-team/results", json={"school_student_id": str(ctx["student"].id), "academic_year": "2026", "term": "Term 1", "subject": f"Race {n}", "max_marks": 100, "marks_obtained": 50})
        result_ids.append(created.json()["id"])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client_b, AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client_c:
        # Log both in first: bcrypt would otherwise stagger the two verifies and hide the race.
        await _login(client_b, reviewer_b.email)
        await _login(client_c, reviewer_c.email)
        for result_id in result_ids:
            responses = await asyncio.gather(
                client_b.post(f"/api/v1/school/academic-team/results/{result_id}/verify"),
                client_c.post(f"/api/v1/school/academic-team/results/{result_id}/verify"),
            )
            assert sorted(r.status_code for r in responses) == [200, 409], f"{result_id}: {[r.status_code for r in responses]}"
            history = (await db_session.scalars(select(SchoolResultStatusHistory).where(SchoolResultStatusHistory.result_id == uuid.UUID(result_id), SchoolResultStatusHistory.to_status == "verified"))).all()
            assert len(history) == 1
