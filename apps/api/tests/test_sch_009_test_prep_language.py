"""SCH-009 -- Test Preparation (IELTS/SAT) and Foreign Language Classes modules.

Both are delivered by the existing `academic_team` role -- the user explicitly chose to
reuse this role rather than create a new one (`DEC-SCOPE-018`). Same portfolio-scoped CRUD
shape as SCH-004/005/006, plus wiring into the SCH-007 overview and SCH-008 timeline. Net-new.
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.identifiers import unique_student_code
from app.core.security import hash_password
from app.models import (
    Notification,
    School,
    SchoolParentLink,
    SchoolStaffAssignment,
    SchoolStudent,
    User,
    UserRoleAssignment,
)

PASSWORD = "Sup3r-Secret-Pass!"


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD, "division": "overseas"})
    assert response.status_code == 200


async def _create_school_with_coordinator(db_session) -> dict:
    admin = User(email=f"sch009-admin-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Overseas Admin", role="overseas_admin", division="overseas", active=True)
    db_session.add(admin)
    await db_session.flush()
    school = School(name=f"SCH-009 Test School {uuid.uuid4().hex[:6]}", created_by_user_id=admin.id)
    db_session.add(school)
    await db_session.flush()
    coordinator = User(email=f"sch009-coord-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Coordinator", role="school_coordinator", division="overseas", active=True, profile={"school_id": str(school.id)})
    db_session.add(coordinator)
    await db_session.flush()
    db_session.add(UserRoleAssignment(user_id=coordinator.id, division="overseas", role="school_coordinator", is_active=True, assigned_by_user_id=admin.id, approval_status="approved"))
    student = SchoolStudent(school_id=school.id, student_code=await unique_student_code(db_session, SchoolStudent.student_code), full_name="Test Student", created_by_user_id=coordinator.id)
    db_session.add(student)
    await db_session.flush()
    parent = User(email=f"sch009-parent-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Parent", role="school_parent", division="overseas", active=True, profile={"school_id": str(school.id)})
    db_session.add(parent)
    await db_session.flush()
    db_session.add(UserRoleAssignment(user_id=parent.id, division="overseas", role="school_parent", is_active=True, assigned_by_user_id=admin.id, approval_status="approved"))
    db_session.add(SchoolParentLink(parent_user_id=parent.id, school_student_id=student.id, linked_by_user_id=coordinator.id))
    await db_session.commit()
    return {"admin": admin, "school": school, "coordinator": coordinator, "student": student, "parent": parent}


async def _add_academic_team_member(db_session, admin, school) -> User:
    member = User(email=f"sch009-academic-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Academic Team Member", role="academic_team", division="overseas", active=True, profile={})
    db_session.add(member)
    await db_session.flush()
    db_session.add(UserRoleAssignment(user_id=member.id, division="overseas", role="academic_team", is_active=True, assigned_by_user_id=admin.id, approval_status="approved"))
    db_session.add(SchoolStaffAssignment(user_id=member.id, school_id=school.id, role="academic_team", assigned_by_user_id=admin.id))
    await db_session.commit()
    return member


# --- Test Preparation ---------------------------------------------------------------------

@pytest.mark.asyncio
async def test_academic_team_starts_test_prep_and_notifies_parent(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    member = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, member.email)
    response = await client.post("/api/v1/school/academic-team/test-prep-records", json={"school_student_id": str(ctx["student"].id), "test_type": "ielts", "target_score": "7.5"})
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "in_progress"

    notes = list((await db_session.scalars(select(Notification).where(Notification.user_id == ctx["parent"].id))).all())
    assert any("preparation started" in n.title for n in notes)


@pytest.mark.asyncio
async def test_recording_an_actual_score_completes_the_record_and_notifies_again(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    member = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, member.email)
    created = await client.post("/api/v1/school/academic-team/test-prep-records", json={"school_student_id": str(ctx["student"].id), "test_type": "sat"})
    record_id = created.json()["id"]

    updated = await client.patch(f"/api/v1/school/academic-team/test-prep-records/{record_id}", json={"actual_score": "1450"})
    assert updated.status_code == 200
    assert updated.json()["status"] == "completed"

    notes = list((await db_session.scalars(select(Notification).where(Notification.user_id == ctx["parent"].id))).all())
    assert any("result recorded" in n.title for n in notes)


@pytest.mark.asyncio
async def test_invalid_test_type_is_rejected(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    member = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, member.email)
    response = await client.post("/api/v1/school/academic-team/test-prep-records", json={"school_student_id": str(ctx["student"].id), "test_type": "toefl"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_academic_team_member_outside_portfolio_cannot_write(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    outsider = User(email=f"sch009-outsider-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Outsider", role="academic_team", division="overseas", active=True, profile={})
    db_session.add(outsider)
    await db_session.flush()
    db_session.add(UserRoleAssignment(user_id=outsider.id, division="overseas", role="academic_team", is_active=True, assigned_by_user_id=ctx["admin"].id, approval_status="approved"))
    await db_session.commit()
    await _login(client, outsider.email)
    response = await client.post("/api/v1/school/academic-team/test-prep-records", json={"school_student_id": str(ctx["student"].id), "test_type": "ielts"})
    assert response.status_code == 403


# --- Foreign Language Classes --------------------------------------------------------------

@pytest.mark.asyncio
async def test_academic_team_starts_language_classes(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    member = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, member.email)
    response = await client.post("/api/v1/school/academic-team/language-records", json={"school_student_id": str(ctx["student"].id), "language": "German", "level": "A1"})
    assert response.status_code == 201, response.text
    assert response.json()["certification_status"] == "not_started"


@pytest.mark.asyncio
async def test_marking_certified_notifies_the_parent(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    member = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, member.email)
    created = await client.post("/api/v1/school/academic-team/language-records", json={"school_student_id": str(ctx["student"].id), "language": "French"})
    record_id = created.json()["id"]

    updated = await client.patch(f"/api/v1/school/academic-team/language-records/{record_id}", json={"certification_status": "certified", "classes_attended": 12})
    assert updated.status_code == 200
    assert updated.json()["certification_status"] == "certified"
    assert updated.json()["classes_attended"] == 12

    notes = list((await db_session.scalars(select(Notification).where(Notification.user_id == ctx["parent"].id))).all())
    assert any("certification earned" in n.title for n in notes)


@pytest.mark.asyncio
async def test_invalid_certification_status_is_rejected(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    member = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, member.email)
    created = await client.post("/api/v1/school/academic-team/language-records", json={"school_student_id": str(ctx["student"].id), "language": "Spanish"})
    record_id = created.json()["id"]
    response = await client.patch(f"/api/v1/school/academic-team/language-records/{record_id}", json={"certification_status": "fluent"})
    assert response.status_code == 422


# --- Read-only cross-role access + overview/timeline wiring --------------------------------

@pytest.mark.asyncio
async def test_coordinator_reads_both_record_types_readonly(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    member = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, member.email)
    await client.post("/api/v1/school/academic-team/test-prep-records", json={"school_student_id": str(ctx["student"].id), "test_type": "ielts"})
    await client.post("/api/v1/school/academic-team/language-records", json={"school_student_id": str(ctx["student"].id), "language": "German"})

    await _login(client, ctx["coordinator"].email)
    test_prep = await client.get("/api/v1/school/test-prep-records")
    language = await client.get("/api/v1/school/language-records")
    assert test_prep.status_code == 200 and len(test_prep.json()) == 1
    assert language.status_code == 200 and len(language.json()) == 1

    write_attempt = await client.post("/api/v1/school/academic-team/test-prep-records", json={"school_student_id": str(ctx["student"].id), "test_type": "sat"})
    assert write_attempt.status_code == 403


@pytest.mark.asyncio
async def test_overview_and_timeline_include_test_prep_and_language(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    member = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, member.email)
    tp = await client.post("/api/v1/school/academic-team/test-prep-records", json={"school_student_id": str(ctx["student"].id), "test_type": "ielts", "target_score": "7.0"})
    await client.patch(f"/api/v1/school/academic-team/test-prep-records/{tp.json()['id']}", json={"actual_score": "7.0"})
    lang = await client.post("/api/v1/school/academic-team/language-records", json={"school_student_id": str(ctx["student"].id), "language": "German"})
    await client.patch(f"/api/v1/school/academic-team/language-records/{lang.json()['id']}", json={"certification_status": "certified"})

    await _login(client, ctx["coordinator"].email)
    overview = await client.get(f"/api/v1/school/students/{ctx['student'].id}/overview")
    assert overview.status_code == 200
    body = overview.json()
    assert body["test_prep"]["status"] == "completed"
    assert body["foreign_language"]["status"] == "certified"

    timeline = await client.get(f"/api/v1/school/students/{ctx['student'].id}/timeline")
    assert timeline.status_code == 200
    types = {e["type"] for e in timeline.json()["events"]}
    assert {"test_prep_started", "test_prep_completed", "language_started", "language_certified"} <= types
