"""SCH-007 -- Parent Portal: child 360 overview + parent notifications.

A Parent sees, for their own child(ren) only: profile, career guidance status, counselling,
recommended careers, psychometric status, Published results, activities attended, and
upcoming sessions -- one endpoint, pure read over the SCH-001/004/005/006 tables. Parents
are notified (in-app row + email delivery record) on the four confirmed triggers:
assessment assigned/report ready, counselling/guidance/recommendation recorded, session
scheduled, result Published. `DEC-SCOPE-015`.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import (
    Notification,
    NotificationDelivery,
    School,
    SchoolAcademicResult,
    SchoolActivity,
    SchoolActivityAttendance,
    SchoolCareerRecord,
    SchoolParentLink,
    SchoolPsychometricRecord,
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
    u = User(email=f"sch007-{role}-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name=full_name, role=role, division="overseas", active=True, profile=profile)
    db_session.add(u)
    await db_session.flush()
    db_session.add(UserRoleAssignment(user_id=u.id, division="overseas", role=role, is_active=True, assigned_by_user_id=(assigned_by or u).id, approval_status="approved"))
    return u


async def _school(db_session) -> dict:
    admin = await _user(db_session, role="overseas_admin", full_name="Overseas Admin")
    school = School(name=f"SCH-007 Test School {uuid.uuid4().hex[:6]}", created_by_user_id=admin.id)
    db_session.add(school)
    await db_session.flush()
    coordinator = await _user(db_session, role="school_coordinator", full_name="Coordinator", school_id=school.id, assigned_by=admin)
    teacher = await _user(db_session, role="school_teacher", full_name="Ms Teacher", school_id=school.id, assigned_by=coordinator)
    student_a = SchoolStudent(school_id=school.id, full_name="Child A", grade_or_class="Grade 8", created_by_user_id=coordinator.id, assigned_teacher_user_id=teacher.id)
    student_b = SchoolStudent(school_id=school.id, full_name="Child B", grade_or_class="Grade 9", created_by_user_id=coordinator.id)
    db_session.add_all([student_a, student_b])
    await db_session.flush()
    parent_a = await _user(db_session, role="school_parent", full_name="Parent of A", school_id=school.id, assigned_by=coordinator)
    parent_b = await _user(db_session, role="school_parent", full_name="Parent of B", school_id=school.id, assigned_by=coordinator)
    db_session.add_all([
        SchoolParentLink(parent_user_id=parent_a.id, school_student_id=student_a.id, linked_by_user_id=coordinator.id),
        SchoolParentLink(parent_user_id=parent_b.id, school_student_id=student_b.id, linked_by_user_id=coordinator.id),
    ])
    await db_session.commit()
    return {"admin": admin, "school": school, "coordinator": coordinator, "teacher": teacher, "student_a": student_a, "student_b": student_b, "parent_a": parent_a, "parent_b": parent_b}


async def _staff(db_session, ctx, role: str) -> User:
    member = await _user(db_session, role=role, full_name=f"{role} member", assigned_by=ctx["admin"])
    db_session.add(SchoolStaffAssignment(user_id=member.id, school_id=ctx["school"].id, role=role, assigned_by_user_id=ctx["admin"].id))
    await db_session.commit()
    return member


async def _notifications_for(db_session, user: User) -> list[Notification]:
    return list((await db_session.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.asc()))).all())


@pytest.mark.asyncio
async def test_parent_sees_their_childs_full_overview(client, db_session):
    ctx = await _school(db_session)
    counselor = await _staff(db_session, ctx, "career_counselor")
    psych = await _staff(db_session, ctx, "psychometric_team")
    a = ctx["student_a"]
    now = datetime.now(UTC)
    past = SchoolActivity(school_id=ctx["school"].id, title="Career Seminar", scheduled_at=now - timedelta(days=3), created_by_user_id=ctx["coordinator"].id)
    future = SchoolActivity(school_id=ctx["school"].id, title="Parent Orientation", scheduled_at=now + timedelta(days=5), created_by_user_id=ctx["coordinator"].id)
    db_session.add_all([past, future])
    await db_session.flush()
    db_session.add_all([
        SchoolActivityAttendance(activity_id=past.id, school_student_id=a.id, present=True, marked_by_user_id=ctx["coordinator"].id),
        SchoolCareerRecord(school_student_id=a.id, career_counselor_user_id=counselor.id, record_type="guidance_session", notes="Explored STEM options"),
        SchoolCareerRecord(school_student_id=a.id, career_counselor_user_id=counselor.id, record_type="counselling_note", notes="Strong analytical skills"),
        SchoolCareerRecord(school_student_id=a.id, career_counselor_user_id=counselor.id, record_type="recommendation", notes="Cyber Security / Computer Science"),
        SchoolPsychometricRecord(school_student_id=a.id, psychometric_team_user_id=psych.id, assessment_type="Aptitude Test", status="completed", report_url="/r.pdf"),
        SchoolAcademicResult(school_student_id=a.id, academic_year="2026-27", term="Term 1", subject="Mathematics", max_marks=100, marks_obtained=88, grade="A", status="published", uploaded_by_user_id=ctx["coordinator"].id, published_at=now),
        SchoolAcademicResult(school_student_id=a.id, academic_year="2026-27", term="Term 1", subject="Physics", max_marks=100, marks_obtained=91, grade="A+", status="draft", uploaded_by_user_id=ctx["coordinator"].id),
    ])
    await db_session.commit()

    await _login(client, ctx["parent_a"].email)
    response = await client.get(f"/api/v1/school/students/{a.id}/overview")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["student"]["full_name"] == "Child A"
    assert body["student"]["school_name"] == ctx["school"].name
    assert body["student"]["assigned_teacher_name"] == "Ms Teacher"
    assert body["career_guidance"]["status"] == "completed" and len(body["career_guidance"]["sessions"]) == 1
    assert body["counselling"]["status"] == "completed" and body["counselling"]["notes"][0]["notes"] == "Strong analytical skills"
    assert [r["notes"] for r in body["recommended_careers"]] == ["Cyber Security / Computer Science"]
    assert body["psychometric"]["status"] == "completed"
    assert body["psychometric"]["assessments"][0]["assessment_type"] == "Aptitude Test"
    # SCH-006-AC02: the Draft Physics result never appears, only the Published Mathematics one.
    assert [r["subject"] for r in body["results"]] == ["Mathematics"]
    assert [x["title"] for x in body["activities"]["attended"]] == ["Career Seminar"]
    assert body["activities"]["attended"][0]["present"] is True
    assert [x["title"] for x in body["activities"]["upcoming"]] == ["Parent Orientation"]


@pytest.mark.asyncio
async def test_parent_cannot_open_an_unlinked_childs_overview_even_at_the_same_school(client, db_session):
    ctx = await _school(db_session)
    await _login(client, ctx["parent_a"].email)
    response = await client.get(f"/api/v1/school/students/{ctx['student_b'].id}/overview")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_a_child_with_no_records_yet_reports_honest_not_started_statuses(client, db_session):
    ctx = await _school(db_session)
    await _login(client, ctx["parent_b"].email)
    response = await client.get(f"/api/v1/school/students/{ctx['student_b'].id}/overview")
    assert response.status_code == 200
    body = response.json()
    assert body["career_guidance"]["status"] == "not_started"
    assert body["counselling"]["status"] == "not_started"
    assert body["psychometric"]["status"] == "not_started"
    assert body["recommended_careers"] == [] and body["results"] == [] and body["activities"]["attended"] == []
    assert body["student"]["assigned_teacher_name"] is None


@pytest.mark.asyncio
async def test_psychometric_assignment_and_report_notify_only_the_linked_parent(client, db_session):
    ctx = await _school(db_session)
    psych = await _staff(db_session, ctx, "psychometric_team")
    await _login(client, psych.email)
    created = await client.post("/api/v1/school/psychometric-team/records", json={"school_student_id": str(ctx["student_a"].id), "assessment_type": "Aptitude Test"})
    assert created.status_code == 201, created.text
    updated = await client.patch(f"/api/v1/school/psychometric-team/records/{created.json()['id']}", json={"report_url": "/local-files/uploads/report.pdf"})
    assert updated.status_code == 200

    a_notes = await _notifications_for(db_session, ctx["parent_a"])
    assert [n.title for n in a_notes] == ["Psychometric assessment assigned to Child A", "Psychometric report ready for Child A"]
    assert a_notes[0].action_url == f"/school/parent/children/{ctx['student_a'].id}"
    # SCH-001-AC03 carried into notifications: the other parent at the same school hears nothing.
    assert await _notifications_for(db_session, ctx["parent_b"]) == []
    # NOT-001: one email delivery row per notification, outcome persisted (no SMTP/webhook in tests).
    deliveries = (await db_session.scalars(select(NotificationDelivery).where(NotificationDelivery.notification_id.in_([n.id for n in a_notes])))).all()
    assert len(deliveries) == 2 and all(d.channel == "email" and d.status in {"not_configured", "sent", "failed"} for d in deliveries)


@pytest.mark.asyncio
async def test_a_second_report_attach_does_not_notify_twice(client, db_session):
    ctx = await _school(db_session)
    psych = await _staff(db_session, ctx, "psychometric_team")
    await _login(client, psych.email)
    created = await client.post("/api/v1/school/psychometric-team/records", json={"school_student_id": str(ctx["student_a"].id), "assessment_type": "Personality Test", "report_url": "/v1.pdf"})
    assert created.json()["status"] == "completed"
    await client.patch(f"/api/v1/school/psychometric-team/records/{created.json()['id']}", json={"report_url": "/v2.pdf"})
    titles = [n.title for n in await _notifications_for(db_session, ctx["parent_a"])]
    assert titles == ["Psychometric report ready for Child A"]


@pytest.mark.asyncio
async def test_career_records_notify_the_parent_per_record_type(client, db_session):
    ctx = await _school(db_session)
    counselor = await _staff(db_session, ctx, "career_counselor")
    await _login(client, counselor.email)
    for record_type in ("guidance_session", "counselling_note", "recommendation"):
        r = await client.post("/api/v1/school/career-counselor/records", json={"school_student_id": str(ctx["student_a"].id), "record_type": record_type, "notes": f"note {record_type}"})
        assert r.status_code == 201, r.text
    titles = [n.title for n in await _notifications_for(db_session, ctx["parent_a"])]
    assert titles == ["Career guidance session recorded for Child A", "Counselling note added for Child A", "Career recommendation added for Child A"]
    assert await _notifications_for(db_session, ctx["parent_b"]) == []


@pytest.mark.asyncio
async def test_scheduling_a_session_notifies_every_parent_at_the_school_once(client, db_session):
    ctx = await _school(db_session)
    # parent_a is also linked to Child B -> still exactly one notification for them.
    db_session.add(SchoolParentLink(parent_user_id=ctx["parent_a"].id, school_student_id=ctx["student_b"].id, linked_by_user_id=ctx["coordinator"].id))
    other = await _school(db_session)  # a parent at a different school must hear nothing
    await _login(client, ctx["coordinator"].email)
    when = (datetime.now(UTC) + timedelta(days=7)).isoformat()
    response = await client.post("/api/v1/school/activities", json={"title": "Career Workshop", "scheduled_at": when})
    assert response.status_code == 201, response.text
    assert [n.title for n in await _notifications_for(db_session, ctx["parent_a"])] == ["Upcoming session: Career Workshop"]
    assert [n.title for n in await _notifications_for(db_session, ctx["parent_b"])] == ["Upcoming session: Career Workshop"]
    assert await _notifications_for(db_session, other["parent_a"]) == []


@pytest.mark.asyncio
async def test_only_the_published_transition_notifies_the_parent(client, db_session):
    ctx = await _school(db_session)
    uploader = await _staff(db_session, ctx, "academic_team")
    approver = await _staff(db_session, ctx, "academic_team")
    await _login(client, uploader.email)
    created = await client.post("/api/v1/school/academic-team/results", json={"school_student_id": str(ctx["student_a"].id), "academic_year": "2026-27", "term": "Term 1", "subject": "Mathematics", "max_marks": 100, "marks_obtained": 88})
    assert created.status_code == 201, created.text
    result_id = created.json()["id"]
    assert await _notifications_for(db_session, ctx["parent_a"]) == []

    await _login(client, approver.email)
    verified = await client.post(f"/api/v1/school/academic-team/results/{result_id}/verify")
    assert verified.status_code == 200, verified.text
    assert await _notifications_for(db_session, ctx["parent_a"]) == []  # Verified is still not Published

    published = await client.post(f"/api/v1/school/academic-team/results/{result_id}/publish")
    assert published.status_code == 200, published.text
    notes = await _notifications_for(db_session, ctx["parent_a"])
    assert [n.title for n in notes] == ["Term 1 Mathematics result published for Child A"]

    # And the parent can now read it in their own notification feed and the child overview.
    await _login(client, ctx["parent_a"].email)
    feed = await client.get("/api/v1/workflows/notifications")
    assert feed.status_code == 200
    assert any(n["title"] == "Term 1 Mathematics result published for Child A" for n in feed.json())
    overview = await client.get(f"/api/v1/school/students/{ctx['student_a'].id}/overview")
    assert [r["subject"] for r in overview.json()["results"]] == ["Mathematics"]


@pytest.mark.asyncio
async def test_teacher_and_coordinator_use_the_same_overview_with_their_own_scope(client, db_session):
    ctx = await _school(db_session)
    await _login(client, ctx["teacher"].email)
    assert (await client.get(f"/api/v1/school/students/{ctx['student_a'].id}/overview")).status_code == 200
    assert (await client.get(f"/api/v1/school/students/{ctx['student_b'].id}/overview")).status_code == 403  # not assigned
    await _login(client, ctx["coordinator"].email)
    assert (await client.get(f"/api/v1/school/students/{ctx['student_b'].id}/overview")).status_code == 200
    other = await _school(db_session)
    assert (await client.get(f"/api/v1/school/students/{other['student_a'].id}/overview")).status_code == 403  # other institution
