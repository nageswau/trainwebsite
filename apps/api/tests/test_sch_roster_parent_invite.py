"""SCH-001/SCH-002/SCH-003 addendum -- roster-driven parent invites.

A Coordinator now enters a parent's name/email directly on the roster (single-add, edit,
or bulk upload) instead of only via the separate Team invite page. If the email doesn't
already belong to a school_parent account at this school, an invite is created and
emailed automatically; accepting it links every student that named that exact email, not
just the one that triggered it. Coordinator-only creation of Teacher/Principal/Parent
accounts was already true before this addendum (SCH-003) -- not re-tested here.
"""

import io
import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import School, SchoolAccountInvite, SchoolParentLink, SchoolStudent, User, UserRoleAssignment

PASSWORD = "Sup3r-Secret-Pass!"


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD, "division": "overseas"})
    assert response.status_code == 200


async def _create_school_with_coordinator(db_session) -> dict:
    admin = User(email=f"sch-roster-admin-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Overseas Admin", role="overseas_admin", division="overseas", active=True)
    db_session.add(admin)
    await db_session.flush()
    school = School(name=f"Roster Test School {uuid.uuid4().hex[:6]}", created_by_user_id=admin.id)
    db_session.add(school)
    await db_session.flush()
    coordinator = User(
        email=f"sch-roster-coord-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD),
        full_name="Test Coordinator", role="school_coordinator", division="overseas", active=True,
        profile={"school_id": str(school.id)},
    )
    db_session.add(coordinator)
    await db_session.flush()
    db_session.add(UserRoleAssignment(user_id=coordinator.id, division="overseas", role="school_coordinator", is_active=True, assigned_by_user_id=admin.id, approval_status="approved"))
    await db_session.commit()
    return {"admin": admin, "school": school, "coordinator": coordinator}


@pytest.mark.asyncio
async def test_a_new_parent_email_on_the_roster_creates_a_pending_invite(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    await _login(client, ctx["coordinator"].email)
    parent_email = f"sch-roster-parent-{uuid.uuid4().hex[:8]}@example.local"

    response = await client.post("/api/v1/school/students", json={"full_name": "Roster Student One", "parent_name": "Parent One", "parent_email": parent_email})
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["parent_status"] == "invited"
    assert data["pending_parent_email"] == parent_email

    invite = await db_session.scalar(select(SchoolAccountInvite).where(SchoolAccountInvite.email == parent_email))
    assert invite is not None
    assert invite.role == "school_parent"
    assert invite.status == "pending"


@pytest.mark.asyncio
async def test_a_second_child_added_while_the_invite_is_pending_reuses_it_not_a_duplicate(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    await _login(client, ctx["coordinator"].email)
    parent_email = f"sch-roster-parent-{uuid.uuid4().hex[:8]}@example.local"

    first = await client.post("/api/v1/school/students", json={"full_name": "Roster Student First", "parent_name": "Parent Two", "parent_email": parent_email})
    assert first.status_code == 201
    assert first.json()["parent_status"] == "invited"

    # A second child added while the first invite is still pending reuses the same invite
    # rather than sending a duplicate email.
    second = await client.post("/api/v1/school/students", json={"full_name": "Roster Student Second", "parent_email": parent_email})
    assert second.status_code == 201
    assert second.json()["parent_status"] == "invite_reused"

    invites = (await db_session.scalars(select(SchoolAccountInvite).where(SchoolAccountInvite.email == parent_email))).all()
    assert len(invites) == 1, "a second roster entry for the same pending email must not send a duplicate invite"


@pytest.mark.asyncio
async def test_accept_flow_links_every_student_with_the_same_pending_email(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    await _login(client, ctx["coordinator"].email)
    parent_email = f"sch-roster-parent-{uuid.uuid4().hex[:8]}@example.local"

    first = await client.post("/api/v1/school/students", json={"full_name": "Sibling One", "parent_name": "Shared Parent", "parent_email": parent_email})
    assert first.status_code == 201, first.text
    first_id = first.json()["id"]
    token = first.json()["development_invite_token"]

    second = await client.post("/api/v1/school/students", json={"full_name": "Sibling Two", "parent_email": parent_email})
    assert second.status_code == 201
    second_id = second.json()["id"]

    await client.post("/api/v1/auth/logout")
    accept = await client.post(f"/api/v1/school/invites/{token}/accept", json={"password": PASSWORD})
    assert accept.status_code == 201, accept.text
    parent_id = uuid.UUID(accept.json()["id"])

    links = (await db_session.scalars(select(SchoolParentLink).where(SchoolParentLink.parent_user_id == parent_id))).all()
    linked_student_ids = {str(l.school_student_id) for l in links}
    assert linked_student_ids == {first_id, second_id}

    s1 = await db_session.get(SchoolStudent, uuid.UUID(first_id))
    s2 = await db_session.get(SchoolStudent, uuid.UUID(second_id))
    assert s1.pending_parent_email is None
    assert s2.pending_parent_email is None


@pytest.mark.asyncio
async def test_an_existing_parent_at_the_same_school_is_linked_immediately_no_invite(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    existing_parent = User(
        email=f"sch-roster-existing-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD),
        full_name="Existing Parent", role="school_parent", division="overseas", active=True,
        profile={"school_id": str(ctx["school"].id)},
    )
    db_session.add(existing_parent)
    await db_session.commit()

    await _login(client, ctx["coordinator"].email)
    response = await client.post("/api/v1/school/students", json={"full_name": "Already Has A Parent", "parent_email": existing_parent.email})
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["parent_status"] == "linked"
    assert data["pending_parent_email"] is None

    link = await db_session.scalar(select(SchoolParentLink).where(SchoolParentLink.parent_user_id == existing_parent.id, SchoolParentLink.school_student_id == uuid.UUID(data["id"])))
    assert link is not None

    invite_count = len((await db_session.scalars(select(SchoolAccountInvite).where(SchoolAccountInvite.email == existing_parent.email))).all())
    assert invite_count == 0, "an already-existing parent account must never trigger an invite email"


@pytest.mark.asyncio
async def test_parent_email_belonging_to_a_non_parent_account_is_rejected(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    other_teacher = User(
        email=f"sch-roster-teacher-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD),
        full_name="Not A Parent", role="school_teacher", division="overseas", active=True,
        profile={"school_id": str(ctx["school"].id)},
    )
    db_session.add(other_teacher)
    await db_session.commit()

    await _login(client, ctx["coordinator"].email)
    response = await client.post("/api/v1/school/students", json={"full_name": "Rejected Parent Student", "parent_email": other_teacher.email})
    assert response.status_code == 422
    assert "not a Parent" in response.json()["detail"]


@pytest.mark.asyncio
async def test_bulk_upload_with_a_new_parent_email_creates_pending_invite_without_blocking_other_rows(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    other_teacher = User(
        email=f"sch-roster-bad-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD),
        full_name="Not A Parent Either", role="school_teacher", division="overseas", active=True,
        profile={"school_id": str(ctx["school"].id)},
    )
    db_session.add(other_teacher)
    await db_session.commit()

    await _login(client, ctx["coordinator"].email)
    good_parent_email = f"sch-roster-bulk-parent-{uuid.uuid4().hex[:8]}@example.local"
    csv_content = (
        "full_name,date_of_birth,grade_or_class,assigned_teacher_email,parent_name,parent_email\n"
        f"Bulk Student Good,,Grade 3,,Bulk Parent,{good_parent_email}\n"
        f"Bulk Student Bad,,Grade 4,,,{other_teacher.email}\n"
    )
    response = await client.post(
        "/api/v1/school/students/bulk-upload",
        files={"file": ("roster.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        headers={"Idempotency-Key": f"bulk-{uuid.uuid4().hex}"},
    )
    assert response.status_code == 201, response.text
    report = response.json()
    assert report["accepted_count"] == 1
    assert report["rejected_count"] == 1
    rejected_row = next(r for r in report["rows"] if r["status"] == "rejected")
    assert "not a Parent" in rejected_row["error_message"]

    accepted_row = next(r for r in report["rows"] if r["status"] == "accepted")
    student = await db_session.get(SchoolStudent, uuid.UUID(accepted_row["created_student_id"]))
    assert student.pending_parent_email == good_parent_email
    invite = await db_session.scalar(select(SchoolAccountInvite).where(SchoolAccountInvite.email == good_parent_email))
    assert invite is not None and invite.full_name == "Bulk Parent"
