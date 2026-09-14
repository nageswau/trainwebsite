"""SCH-008 -- Student Journey Timeline (narrow version): a chronological list of events
already recorded for one student, built only from already-built modules (`SCH-001`/`004`/
`005`/`006`). Same own-scope loader as `SCH-007`'s overview -- a Parent sees only their own
child's timeline, a Teacher their assigned student's, Coordinator/Principal their own
institution's. `DEC-SCOPE-015`.
"""

import uuid
from datetime import UTC, datetime

import pytest

from app.core.security import hash_password
from app.models import (
    School,
    SchoolActivity,
    SchoolActivityAttendance,
    SchoolParentLink,
    SchoolStaffAssignment,
    SchoolStudent,
    User,
    UserRoleAssignment,
)

PASSWORD = "Sup3r-Secret-Pass!"


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD, "division": "overseas"})
    assert response.status_code == 200, response.text


async def _user(db_session, *, role: str, full_name: str, school_id=None, assigned_by=None) -> User:
    profile = {"school_id": str(school_id)} if school_id else {}
    u = User(email=f"sch008-{role}-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name=full_name, role=role, division="overseas", active=True, profile=profile)
    db_session.add(u)
    await db_session.flush()
    db_session.add(UserRoleAssignment(user_id=u.id, division="overseas", role=role, is_active=True, assigned_by_user_id=(assigned_by or u).id, approval_status="approved"))
    return u


async def _school(db_session) -> dict:
    admin = await _user(db_session, role="overseas_admin", full_name="Overseas Admin")
    school = School(name=f"SCH-008 Test School {uuid.uuid4().hex[:6]}", created_by_user_id=admin.id)
    db_session.add(school)
    await db_session.flush()
    coordinator = await _user(db_session, role="school_coordinator", full_name="Coordinator", school_id=school.id, assigned_by=admin)
    teacher = await _user(db_session, role="school_teacher", full_name="Ms Teacher", school_id=school.id, assigned_by=coordinator)
    student_a = SchoolStudent(school_id=school.id, full_name="Child A", grade_or_class="Grade 8", created_by_user_id=coordinator.id, assigned_teacher_user_id=teacher.id)
    student_b = SchoolStudent(school_id=school.id, full_name="Child B", grade_or_class="Grade 9", created_by_user_id=coordinator.id)
    db_session.add_all([student_a, student_b])
    await db_session.flush()
    parent_a = await _user(db_session, role="school_parent", full_name="Parent of A", school_id=school.id, assigned_by=coordinator)
    db_session.add(SchoolParentLink(parent_user_id=parent_a.id, school_student_id=student_a.id, linked_by_user_id=coordinator.id))
    await db_session.commit()
    return {"admin": admin, "school": school, "coordinator": coordinator, "teacher": teacher, "student_a": student_a, "student_b": student_b, "parent_a": parent_a}


async def _staff(db_session, ctx, role: str) -> User:
    member = await _user(db_session, role=role, full_name=f"{role} member", assigned_by=ctx["admin"])
    db_session.add(SchoolStaffAssignment(user_id=member.id, school_id=ctx["school"].id, role=role, assigned_by_user_id=ctx["admin"].id))
    await db_session.commit()
    return member


@pytest.mark.asyncio
async def test_a_new_students_timeline_has_only_the_profile_created_event(client, db_session):
    ctx = await _school(db_session)
    await _login(client, ctx["parent_a"].email)
    response = await client.get(f"/api/v1/school/students/{ctx['student_a'].id}/timeline")
    assert response.status_code == 200, response.text
    events = response.json()["events"]
    assert len(events) == 1
    assert events[0]["category"] == "profile" and events[0]["type"] == "profile_created"
    assert events[0]["detail"] == "Added to Grade 8"


@pytest.mark.asyncio
async def test_timeline_events_are_returned_in_real_chronological_order(client, db_session):
    ctx = await _school(db_session)
    counselor = await _staff(db_session, ctx, "career_counselor")
    psych = await _staff(db_session, ctx, "psychometric_team")
    academic = await _staff(db_session, ctx, "academic_team")
    approver = await _staff(db_session, ctx, "academic_team")
    a = ctx["student_a"]

    await _login(client, counselor.email)
    r1 = await client.post("/api/v1/school/career-counselor/records", json={"school_student_id": str(a.id), "record_type": "guidance_session", "notes": "Explored STEM options"})
    assert r1.status_code == 201, r1.text

    await _login(client, psych.email)
    r2 = await client.post("/api/v1/school/psychometric-team/records", json={"school_student_id": str(a.id), "assessment_type": "Aptitude Test"})
    assert r2.status_code == 201, r2.text
    record_id = r2.json()["id"]
    r3 = await client.patch(f"/api/v1/school/psychometric-team/records/{record_id}", json={"report_url": "/report.pdf"})
    assert r3.status_code == 200, r3.text

    await _login(client, counselor.email)
    r4 = await client.post("/api/v1/school/career-counselor/records", json={"school_student_id": str(a.id), "record_type": "recommendation", "notes": "Cyber Security"})
    assert r4.status_code == 201, r4.text

    await _login(client, academic.email)
    r5 = await client.post("/api/v1/school/academic-team/results", json={"school_student_id": str(a.id), "academic_year": "2026-27", "term": "Term 1", "subject": "Mathematics", "max_marks": 100, "marks_obtained": 88, "grade": "A"})
    assert r5.status_code == 201, r5.text
    result_id = r5.json()["id"]
    await _login(client, approver.email)
    assert (await client.post(f"/api/v1/school/academic-team/results/{result_id}/verify")).status_code == 200
    assert (await client.post(f"/api/v1/school/academic-team/results/{result_id}/publish")).status_code == 200

    # Scheduled "now" (after every event above in real wall-clock time) -- the timeline
    # orders activities by their real-world scheduled_at, not by write order, so a session
    # actually held earlier would sort earlier even if attendance was marked later.
    activity = SchoolActivity(school_id=ctx["school"].id, title="Career Seminar", scheduled_at=datetime.now(UTC), created_by_user_id=ctx["coordinator"].id)
    db_session.add(activity)
    await db_session.flush()
    db_session.add(SchoolActivityAttendance(activity_id=activity.id, school_student_id=a.id, present=True, marked_by_user_id=ctx["coordinator"].id))
    await db_session.commit()

    await _login(client, ctx["parent_a"].email)
    response = await client.get(f"/api/v1/school/students/{a.id}/timeline")
    assert response.status_code == 200, response.text
    events = response.json()["events"]

    types = [e["type"] for e in events]
    assert types == [
        "profile_created", "guidance_session", "psychometric_assigned",
        "psychometric_report", "recommendation", "result_published", "activity_attended",
    ], types
    dates = [e["date"] for e in events]
    assert dates == sorted(dates), "events must be in ascending chronological order"

    result_event = next(e for e in events if e["type"] == "result_published")
    assert result_event["category"] == "academic" and result_event["detail"] == "Term 1 Mathematics -- A"
    guidance_event = next(e for e in events if e["type"] == "guidance_session")
    assert guidance_event["category"] == "career" and guidance_event["detail"] == "Explored STEM options"
    attended_event = next(e for e in events if e["type"] == "activity_attended")
    assert attended_event["category"] == "activity" and attended_event["title"] == "Attended Career Seminar"


@pytest.mark.asyncio
async def test_a_draft_or_verified_result_never_appears_on_the_timeline(client, db_session):
    ctx = await _school(db_session)
    academic = await _staff(db_session, ctx, "academic_team")
    await _login(client, academic.email)
    created = await client.post("/api/v1/school/academic-team/results", json={"school_student_id": str(ctx["student_a"].id), "academic_year": "2026-27", "term": "Term 1", "subject": "Physics", "max_marks": 100, "marks_obtained": 91})
    assert created.status_code == 201, created.text

    await _login(client, ctx["parent_a"].email)
    response = await client.get(f"/api/v1/school/students/{ctx['student_a'].id}/timeline")
    events = response.json()["events"]
    assert not any(e["type"] == "result_published" for e in events)
    assert [e["type"] for e in events] == ["profile_created"]


@pytest.mark.asyncio
async def test_a_psychometric_record_assigned_without_a_report_produces_only_one_event(client, db_session):
    ctx = await _school(db_session)
    psych = await _staff(db_session, ctx, "psychometric_team")
    await _login(client, psych.email)
    created = await client.post("/api/v1/school/psychometric-team/records", json={"school_student_id": str(ctx["student_a"].id), "assessment_type": "Personality Test"})
    assert created.status_code == 201, created.text

    await _login(client, ctx["parent_a"].email)
    response = await client.get(f"/api/v1/school/students/{ctx['student_a'].id}/timeline")
    events = response.json()["events"]
    assert [e["type"] for e in events] == ["profile_created", "psychometric_assigned"]


@pytest.mark.asyncio
async def test_parent_cannot_open_an_unlinked_childs_timeline_even_at_the_same_school(client, db_session):
    ctx = await _school(db_session)
    await _login(client, ctx["parent_a"].email)
    response = await client.get(f"/api/v1/school/students/{ctx['student_b'].id}/timeline")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_teacher_and_coordinator_use_the_same_endpoint_with_their_own_scope(client, db_session):
    ctx = await _school(db_session)
    await _login(client, ctx["teacher"].email)
    assert (await client.get(f"/api/v1/school/students/{ctx['student_a'].id}/timeline")).status_code == 200
    assert (await client.get(f"/api/v1/school/students/{ctx['student_b'].id}/timeline")).status_code == 403  # not assigned
    await _login(client, ctx["coordinator"].email)
    assert (await client.get(f"/api/v1/school/students/{ctx['student_b'].id}/timeline")).status_code == 200
    other = await _school(db_session)
    assert (await client.get(f"/api/v1/school/students/{other['student_a'].id}/timeline")).status_code == 403  # other institution


@pytest.mark.asyncio
async def test_career_counselor_and_psychometric_team_have_no_scope_on_this_endpoint(client, db_session):
    """SCH-008 reuses SCH-001/007's four-school-side-role scope loader, not the three
    specialized service-delivery roles' own portfolio mechanism -- a Career Counselor writes
    the events but does not read this student-facing timeline view themselves."""
    ctx = await _school(db_session)
    counselor = await _staff(db_session, ctx, "career_counselor")
    await _login(client, counselor.email)
    response = await client.get(f"/api/v1/school/students/{ctx['student_a'].id}/timeline")
    assert response.status_code == 403
