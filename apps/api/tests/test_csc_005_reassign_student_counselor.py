"""csc-005 (DEC-SCOPE-230; W3, W6) -- the Overseas Admin moves an overseas student to another active overseas counselor
(PUT /admin/users/{id}/counselor), AGN-023's rules for the student-level link (csc-001). The Overseas Admin's Users directory shows each
overseas student's counselor with the control -- the Students page lists applications (AGN-023 H11), so a walk-in with none is not there."""

import uuid

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, Notification, OverseasStudentCounselor
from tests.agn001_helpers import login, mk_user, uniq

LOOKUP = "/api/v1/lookups/overseas-students"


def url(student_id) -> str:
    return f"/api/v1/admin/users/{student_id}/counselor"


async def link(db, student, counselor) -> None:
    db.add(OverseasStudentCounselor(student_user_id=student.id, counselor_user_id=counselor.id, assigned_by_user_id=counselor.id))
    await db.commit()


async def linked_counselor(db, student):
    row = await db.scalar(select(OverseasStudentCounselor).where(OverseasStudentCounselor.student_user_id == student.id).execution_options(populate_existing=True))
    return row.counselor_user_id if row else None


async def notes(db, user, title: str) -> int:
    return await db.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == user.id, Notification.title == title))


@pytest.mark.asyncio
async def test_the_overseas_admin_moves_a_student_to_another_counselor(client, db_session):
    student = await mk_user(db_session, role="overseas_student", full_name=f"{uniq('c5')} Walk-in")
    old = await mk_user(db_session, role="counselor", full_name="Old Counselor")
    new = await mk_user(db_session, role="counselor", full_name="New Counselor")
    admin = await mk_user(db_session, role="overseas_admin")
    await link(db_session, student, old)
    await login(client, admin.email)
    response = await client.put(url(student.id), json={"counselor_id": str(new.id)})
    assert response.status_code == 200, response.text
    assert response.json() == {"id": str(student.id), "counselor_id": str(new.id), "counselor_name": "New Counselor", "changed": True}
    assert await linked_counselor(db_session, student) == new.id
    row = await db_session.scalar(select(OverseasStudentCounselor).where(OverseasStudentCounselor.student_user_id == student.id))
    assert row.assigned_by_user_id == admin.id
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "overseas.student.counselor_assign", AuditLog.entity_id == str(student.id)))
    assert audit.user_id == admin.id and audit.metadata_json == {"from_counselor_id": str(old.id), "to_counselor_id": str(new.id)}
    assert await notes(db_session, new, "Student assigned to you") == 1
    assert await notes(db_session, old, "Student reassigned") == 1

    await login(client, new.email)
    assert [i["id"] for i in (await client.get(LOOKUP, params={"q": student.full_name})).json()["items"]] == [str(student.id)]
    await login(client, old.email)
    assert (await client.get(LOOKUP, params={"q": student.full_name})).json()["items"] == []


@pytest.mark.asyncio
async def test_a_student_with_no_counselor_yet_is_assigned(client, db_session):
    student = await mk_user(db_session, role="overseas_student")
    counselor = await mk_user(db_session, role="counselor")
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    response = await client.put(url(student.id), json={"counselor_id": str(counselor.id)})
    assert response.status_code == 200 and response.json()["changed"] is True
    assert await linked_counselor(db_session, student) == counselor.id
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "overseas.student.counselor_assign", AuditLog.entity_id == str(student.id)))
    assert audit.metadata_json == {"from_counselor_id": None, "to_counselor_id": str(counselor.id)}


@pytest.mark.asyncio
async def test_the_same_counselor_changes_nothing(client, db_session):
    student = await mk_user(db_session, role="overseas_student")
    counselor = await mk_user(db_session, role="counselor")
    admin = await mk_user(db_session, role="overseas_admin")
    await link(db_session, student, counselor)
    await login(client, admin.email)
    response = await client.put(url(student.id), json={"counselor_id": str(counselor.id)})
    assert response.status_code == 200 and response.json()["changed"] is False
    assert await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "overseas.student.counselor_assign", AuditLog.entity_id == str(student.id))) == 0
    assert await notes(db_session, counselor, "Student assigned to you") == 0


@pytest.mark.asyncio
async def test_only_an_active_overseas_counselor_can_receive_the_student(client, db_session):
    student = await mk_user(db_session, role="overseas_student")
    admin = await mk_user(db_session, role="overseas_admin")
    inactive = await mk_user(db_session, role="counselor", active=False)
    it_counselor = await mk_user(db_session, role="counselor", division="it")
    telecaller = await mk_user(db_session, role="telecaller")
    await login(client, admin.email)
    for target in (inactive.id, it_counselor.id, telecaller.id, uuid.uuid4()):
        response = await client.put(url(student.id), json={"counselor_id": str(target)})
        assert response.status_code == 422 and response.json()["detail"] == "Choose an active overseas counselor"
    assert (await client.put(url(student.id), json={})).status_code == 422
    assert await linked_counselor(db_session, student) is None


@pytest.mark.asyncio
async def test_only_an_overseas_student_can_be_reassigned(client, db_session):
    counselor = await mk_user(db_session, role="counselor")
    admin = await mk_user(db_session, role="overseas_admin")
    it_student = await mk_user(db_session, role="it_student", division="it")
    await login(client, admin.email)
    for target in (counselor.id, it_student.id, admin.id, uuid.uuid4()):
        response = await client.put(url(target), json={"counselor_id": str(counselor.id)})
        assert response.status_code == 404 and response.json()["detail"] == "Student not found"


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("super_admin", "global"), ("it_admin", "it"), ("counselor", "overseas"), ("overseas_student", "overseas"), ("agent", "overseas")])
async def test_everyone_but_the_overseas_admin_is_403(client, db_session, role, division):
    student = await mk_user(db_session, role="overseas_student")
    counselor = await mk_user(db_session, role="counselor")
    actor = await mk_user(db_session, role=role, division=division)
    await login(client, actor.email, division="it" if division == "it" else "overseas")
    response = await client.put(url(student.id), json={"counselor_id": str(counselor.id)})
    assert response.status_code == 403 and response.json()["detail"] == "Only the Overseas Admin can assign a counselor"


@pytest.mark.asyncio
async def test_anonymous_is_401(client):
    assert (await client.put(url(uuid.uuid4()), json={"counselor_id": str(uuid.uuid4())})).status_code == 401


# --- the Users directory ---------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_overseas_admins_users_directory_shows_a_students_counselor_and_the_control(client, db_session):
    student = await mk_user(db_session, role="overseas_student", full_name=f"{uniq('c5')} Listed")
    counselor = await mk_user(db_session, role="counselor", full_name="Linked Counselor")
    await link(db_session, student, counselor)
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    body = (await client.get("/api/v1/portal/overseas/overseas_admin/users")).json()
    columns = {c["key"]: c.get("type") for c in body["columns"]}
    assert columns["counselor"] is None and columns["assign"] == "assign_student_counselor"
    row = next(r for r in body["rows"] if r["id"] == str(student.id))
    assert (row["counselor"], row["counselor_id"], row["assign"]) == ("Linked Counselor", str(counselor.id), str(student.id))
    unlinked = next(r for r in body["rows"] if r["role"] == "overseas_student" and r["counselor_id"] is None)
    assert unlinked["counselor"] == "Not assigned" and unlinked["assign"] == unlinked["id"]
    staff = next(r for r in body["rows"] if r["id"] == str(admin.id))
    assert (staff["counselor"], staff["assign"]) == (None, None)  # staff rows: no counsellor, no control


@pytest.mark.asyncio
async def test_other_user_sections_are_unchanged(client, db_session):
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    keys = [c["key"] for c in (await client.get("/api/v1/portal/overseas/overseas_admin/counselors")).json()["columns"]]
    assert keys == ["id", "name", "email", "role", "active", "setup"]
    super_admin = await mk_user(db_session, role="super_admin", division="global")
    await login(client, super_admin.email)
    keys = [c["key"] for c in (await client.get("/api/v1/portal/overseas/admin/users")).json()["columns"]]
    assert "assign" not in keys  # C13: the control is the Overseas Admin's only
