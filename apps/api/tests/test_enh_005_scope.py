import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from enh005_helpers import login, mk_result, mk_school, mk_staff, mk_student, mk_user, move_student_directly
from sqlalchemy import select

from app.models import SchoolAccountInvite, SchoolParentLink, SchoolStudent, User

# ENH-005 spec §8 / security review S2: a parent's scope is their LINKS, not their school (a transferred child lives at
# another school than the parent's account), and `withdrawn` results are invisible. Everything here runs against Postgres.

NOT_LINKED = "This student is not linked to your account"
DIFFERENT_INSTITUTION = "This student is at a different institution"


async def _moved_child_world(db_session):
    """Parent P (account at school A) linked to child C, who now lives at school B."""
    a = await mk_school(db_session, label="A")
    b = await mk_school(db_session, label="B", students=0)
    child = a["students"][0]
    await move_student_directly(db_session, child, b["school"])
    return a, b, child


@pytest.mark.asyncio
async def test_a_parent_reads_a_linked_child_who_lives_at_another_school(client, db_session):
    a, b, child = await _moved_child_world(db_session)
    await login(client, a["parent"].email)

    listing = await client.get("/api/v1/school/students")
    assert listing.status_code == 200, listing.text
    assert [s["id"] for s in listing.json()] == [str(child.id)]
    for path in ("", "/overview", "/timeline"):
        response = await client.get(f"/api/v1/school/students/{child.id}{path}")
        assert response.status_code == 200, (path, response.text)


@pytest.mark.asyncio
async def test_a_parent_still_cannot_read_an_unlinked_student_and_keeps_todays_messages(client, db_session):
    a = await mk_school(db_session, label="A", students=2)
    b = await mk_school(db_session, label="B")
    same_school_unlinked = a["students"][1]
    other_school = b["students"][0]
    await login(client, a["parent"].email)

    r = await client.get(f"/api/v1/school/students/{same_school_unlinked.id}")
    assert (r.status_code, r.json()["detail"]) == (403, NOT_LINKED)
    r = await client.get(f"/api/v1/school/students/{other_school.id}")
    assert (r.status_code, r.json()["detail"]) == (403, DIFFERENT_INSTITUTION)
    listing = await client.get("/api/v1/school/students")
    assert [s["id"] for s in listing.json()] == [str(a["students"][0].id)]


@pytest.mark.asyncio
async def test_published_results_and_other_readers_follow_the_link(client, db_session):
    a, b, child = await _moved_child_world(db_session)
    staff = await mk_staff(db_session, b["school"], a["admin"])
    await mk_result(db_session, child, staff, status="published")
    await login(client, a["parent"].email)

    response = await client.get("/api/v1/school/results")
    assert response.status_code == 200, response.text
    assert [r["school_student_id"] for r in response.json()] == [str(child.id)]


@pytest.mark.asyncio
async def test_teacher_and_principal_scopes_are_unchanged_by_the_parent_change(client, db_session):
    a = await mk_school(db_session, label="A", students=2)
    b = await mk_school(db_session, label="B")
    await login(client, a["principal"].email)
    listing = await client.get("/api/v1/school/students")
    assert {s["id"] for s in listing.json()} == {str(s.id) for s in a["students"]}
    assert (await client.get(f"/api/v1/school/students/{b['students'][0].id}")).status_code == 403
    await login(client, a["teacher"].email)
    assert {s["id"] for s in (await client.get("/api/v1/school/students")).json()} == {str(a["students"][0].id)}


@pytest.mark.asyncio
async def test_withdrawn_results_are_hidden_from_the_academic_team_and_cannot_be_advanced(client, db_session):
    a = await mk_school(db_session, label="A")
    student = a["students"][0]
    uploader = await mk_staff(db_session, a["school"], a["admin"])
    reviewer = await mk_staff(db_session, a["school"], a["admin"])
    withdrawn = await mk_result(db_session, student, uploader, status="withdrawn", subject="Withdrawn subject")
    await mk_result(db_session, student, uploader, status="draft", subject="Live subject")
    await login(client, uploader.email)

    listing = await client.get("/api/v1/school/academic-team/results")
    assert [r["subject"] for r in listing.json()] == ["Live subject"]
    progress = (await client.get("/api/v1/school/academic-team/progress")).json()
    assert [(p["school_student_id"], p["result_count"]) for p in progress] == [(str(student.id), 1)]
    edit = await client.patch(f"/api/v1/school/academic-team/results/{withdrawn.id}", json={"subject": "x"})
    assert edit.status_code == 409, edit.text
    await login(client, reviewer.email)
    for action in ("verify", "publish"):
        response = await client.post(f"/api/v1/school/academic-team/results/{withdrawn.id}/{action}")
        assert response.status_code == 409, (action, response.text)


# ---- S2: every way a parent<->student link is created still refuses a cross-school pair --------------------------


@pytest.mark.asyncio
async def test_link_parent_accepts_a_parent_already_linked_at_another_school(client, db_session):
    a = await mk_school(db_session, label="A")
    b = await mk_school(db_session, label="B")
    await login(client, a["coordinator"].email)

    response = await client.post(f"/api/v1/school/students/{a['students'][0].id}/parents", json={"parent_email": b["parent"].email})

    assert response.status_code == 201, response.text
    link = await db_session.scalar(select(SchoolParentLink).where(SchoolParentLink.parent_user_id == b["parent"].id, SchoolParentLink.school_student_id == a["students"][0].id))
    assert link is not None


@pytest.mark.asyncio
async def test_link_parent_rejects_an_unknown_parent_email(client, db_session):
    a = await mk_school(db_session, label="A")
    await login(client, a["coordinator"].email)

    response = await client.post(f"/api/v1/school/students/{a['students'][0].id}/parents", json={"parent_email": "never-used-email@example.com"})

    assert response.status_code == 422, response.text
    assert "parent_email must belong to an existing Parent account" in response.text


@pytest.mark.asyncio
async def test_link_parent_rejects_a_parent_email_belonging_to_a_non_parent_account(client, db_session):
    a = await mk_school(db_session, label="A")
    await login(client, a["coordinator"].email)
    teacher = a["teacher"]

    response = await client.post(f"/api/v1/school/students/{a['students'][0].id}/parents", json={"parent_email": teacher.email})

    assert response.status_code == 422, response.text
    assert "belongs to an existing account that is not a Parent" in response.text


@pytest.mark.asyncio
async def test_adding_a_student_at_school_a_can_use_a_parent_already_linked_at_school_b(client, db_session):
    a = await mk_school(db_session, label="A")
    b = await mk_school(db_session, label="B")
    await login(client, a["coordinator"].email)
    name = f"Cross Link {uuid.uuid4().hex[:6]}"

    response = await client.post("/api/v1/school/students", json={"full_name": name, "parent_email": b["parent"].email})

    assert response.status_code == 201, response.text
    assert response.json()["parent_status"] == "linked"
    student = await db_session.scalar(select(SchoolStudent).where(SchoolStudent.full_name == name))
    assert student is not None
    link = await db_session.scalar(select(SchoolParentLink).where(SchoolParentLink.parent_user_id == b["parent"].id, SchoolParentLink.school_student_id == student.id))
    assert link is not None


@pytest.mark.asyncio
async def test_accepting_an_invite_links_only_students_of_the_invites_own_school(client, db_session):
    a = await mk_school(db_session, label="A")
    b = await mk_school(db_session, label="B")
    email = f"enh005-invited-{uuid.uuid4().hex[:8]}@example.local"
    own = await mk_student(db_session, a["school"], a["coordinator"], "own")
    foreign = await mk_student(db_session, b["school"], b["coordinator"], "foreign")
    own.pending_parent_email = email
    foreign.pending_parent_email = email
    token = uuid.uuid4().hex
    db_session.add(
        SchoolAccountInvite(
            school_id=a["school"].id,
            role="school_parent",
            invited_by_user_id=a["coordinator"].id,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            email=email,
            full_name="Invited Parent",
            status="pending",
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
    )
    await db_session.commit()

    response = await client.post(f"/api/v1/school/invites/{token}/accept", json={"password": "Sup3r-Secret-Pass!"})
    assert response.status_code == 201, response.text

    account = await db_session.scalar(select(User).where(User.email == email))
    linked = {row.school_student_id for row in (await db_session.scalars(select(SchoolParentLink).where(SchoolParentLink.parent_user_id == account.id))).all()}
    assert linked == {own.id}
    assert foreign.id not in linked
