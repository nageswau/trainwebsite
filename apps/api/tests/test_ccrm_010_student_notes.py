"""ccrm-010 (DEC-SCOPE-241, N1-N5) -- append-only internal notes on an overseas student, optionally on one of the student's applications:
GET/POST /counselor/students/{id}/notes. The overseas counselor within csc-001 scope and the Overseas Admin read and write; the student,
the agent and every other role never see them. The Students section and the Overseas Admin's Users directory link to the notes page."""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models import OverseasStudentCounselor, OverseasStudentNote
from tests.agn001_helpers import login, mk_user, uniq
from tests.enh031_helpers import mk_application, mk_university

PORTAL = "/api/v1/portal/overseas/{}/{}"


def url(student_id) -> str:
    return f"/api/v1/counselor/students/{student_id}/notes"


async def link(db, student, counselor) -> None:
    db.add(OverseasStudentCounselor(student_user_id=student.id, counselor_user_id=counselor.id, assigned_by_user_id=counselor.id))
    await db.commit()


@pytest_asyncio.fixture
async def world(db_session):
    counselor = await mk_user(db_session, role="counselor", full_name="Nora Counselor")
    other = await mk_user(db_session, role="counselor", full_name="Omar Counselor")
    admin = await mk_user(db_session, role="overseas_admin", full_name="Ada Admin")
    student = await mk_user(db_session, role="overseas_student", full_name=f"{uniq('n10')} Student")
    university = await mk_university(db_session, name=uniq("Notes Uni"))
    own = await mk_application(db_session, student=student, university=university, counselor=counselor, reference="REF-1")
    foreign = await mk_application(db_session, student=student, university=await mk_university(db_session), counselor=other)
    return {"counselor": counselor, "other": other, "admin": admin, "student": student, "university": university, "own": own, "foreign": foreign}


@pytest.mark.asyncio
async def test_counselor_adds_and_reads_a_note_on_their_student(client, db_session, world):
    await login(client, world["counselor"].email)
    response = await client.post(url(world["student"].id), json={"body": "  First counselling call: wants UK, Sep 2027.  "})
    assert response.status_code == 201, response.text
    note = response.json()
    assert note["body"] == "First counselling call: wants UK, Sep 2027."
    assert note["author_name"] == "Nora Counselor" and note["author_role"] == "counselor" and note["application"] is None
    assert note["id"] and note["created_at"]

    data = (await client.get(url(world["student"].id))).json()
    assert data["student"] == {"id": str(world["student"].id), "full_name": world["student"].full_name, "student_code": None}
    assert data["total"] == 1 and [i["id"] for i in data["items"]] == [note["id"]]
    assert data["applications"] == [{"id": str(world["own"].id), "label": f"{world['university'].name} · REF-1"}]  # N3: only their own
    row = await db_session.scalar(select(OverseasStudentNote).where(OverseasStudentNote.id == uuid.UUID(note["id"])))
    assert row.author_user_id == world["counselor"].id and row.student_user_id == world["student"].id


@pytest.mark.asyncio
async def test_a_note_on_the_counselors_own_application(client, world):
    await login(client, world["counselor"].email)
    response = await client.post(url(world["student"].id), json={"body": "Offer chased", "application_id": str(world["own"].id)})
    assert response.status_code == 201, response.text
    assert response.json()["application"] == {"id": str(world["own"].id), "label": f"{world['university'].name} · REF-1"}


@pytest.mark.asyncio
@pytest.mark.parametrize("which", ["foreign", "elsewhere", "unknown"])
async def test_a_counselor_cannot_attach_another_application(client, db_session, world, which):
    if which == "elsewhere":  # the counselor's own application, but for another student
        other_student = await mk_user(db_session, role="overseas_student")
        app_id = (await mk_application(db_session, student=other_student, university=world["university"], counselor=world["counselor"])).id
    else:
        app_id = world["foreign"].id if which == "foreign" else uuid.uuid4()
    await login(client, world["counselor"].email)
    response = await client.post(url(world["student"].id), json={"body": "x", "application_id": str(app_id)})
    assert response.status_code == 422 and response.json()["detail"] == "Choose one of this student's applications"
    assert await db_session.scalar(select(func.count()).select_from(OverseasStudentNote).where(OverseasStudentNote.student_user_id == world["student"].id)) == 0


@pytest.mark.asyncio
async def test_a_linked_walk_in_student_is_in_scope(client, db_session, world):
    walk_in = await mk_user(db_session, role="overseas_student", full_name="Walk In")
    await link(db_session, walk_in, world["counselor"])
    await login(client, world["counselor"].email)
    assert (await client.post(url(walk_in.id), json={"body": "Walked in today"})).status_code == 201
    data = (await client.get(url(walk_in.id))).json()
    assert data["total"] == 1 and data["applications"] == []


@pytest.mark.asyncio
async def test_out_of_scope_unknown_and_non_student_are_404(client, db_session, world):
    stranger = await mk_user(db_session, role="overseas_student")
    await login(client, world["counselor"].email)
    for target in (stranger.id, uuid.uuid4(), world["other"].id):
        assert (await client.get(url(target))).status_code == 404
        response = await client.post(url(target), json={"body": "x"})
        assert response.status_code == 404 and response.json()["detail"] == "Student not found"
    await login(client, world["admin"].email)
    assert (await client.get(url(world["other"].id))).status_code == 404  # admin: only overseas students


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{"body": "   "}, {"body": ""}, {"body": "x" * 4001}, {}, {"body": "x", "author_user_id": str(uuid.uuid4())}, {"body": "x", "application_id": "nope"}])
async def test_invalid_bodies_are_422(client, world, payload):
    await login(client, world["counselor"].email)
    assert (await client.post(url(world["student"].id), json=payload)).status_code == 422


@pytest.mark.asyncio
async def test_the_overseas_admin_reads_and_writes_any_student_and_application(client, db_session, world):
    await login(client, world["counselor"].email)
    await client.post(url(world["student"].id), json={"body": "Counselor note"})
    stranger = await mk_user(db_session, role="overseas_student")
    await login(client, world["admin"].email)
    response = await client.post(url(world["student"].id), json={"body": "Escalated: fee query", "application_id": str(world["foreign"].id)})
    assert response.status_code == 201, response.text
    assert response.json()["author_role"] == "overseas_admin"
    data = (await client.get(url(world["student"].id))).json()
    assert [i["body"] for i in data["items"]] == ["Escalated: fee query", "Counselor note"]  # newest first
    assert {a["id"] for a in data["applications"]} == {str(world["own"].id), str(world["foreign"].id)}
    assert (await client.post(url(stranger.id), json={"body": "Any student"})).status_code == 201


@pytest.mark.asyncio
async def test_history_survives_a_reassignment(client, db_session, world):
    walk_in = await mk_user(db_session, role="overseas_student")
    await link(db_session, walk_in, world["counselor"])
    await login(client, world["counselor"].email)
    await client.post(url(walk_in.id), json={"body": "Before the move"})
    await login(client, world["admin"].email)
    assert (await client.put(f"/api/v1/admin/users/{walk_in.id}/counselor", json={"counselor_id": str(world["other"].id), "reason": "Workload balance"})).status_code == 200
    await login(client, world["other"].email)
    items = (await client.get(url(walk_in.id))).json()["items"]
    assert [(i["body"], i["author_name"]) for i in items] == [("Before the move", "Nora Counselor")]
    await login(client, world["counselor"].email)
    assert (await client.get(url(walk_in.id))).status_code == 404  # no longer theirs


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "division"), [("overseas_student", "overseas"), ("agent", "overseas"), ("university_rep", "overseas"), ("counselor", "it"), ("super_admin", "global"), ("it_admin", "it")]
)
async def test_other_roles_are_403(client, db_session, world, role, division):
    user = world["student"] if role == "overseas_student" else await mk_user(db_session, role=role, division=division)
    await login(client, user.email, division=division if division != "global" else "overseas")
    assert (await client.get(url(world["student"].id))).status_code == 403
    assert (await client.post(url(world["student"].id), json={"body": "x"})).status_code == 403


@pytest.mark.asyncio
async def test_anonymous_is_401(client, world):
    assert (await client.get(url(world["student"].id))).status_code == 401


@pytest.mark.asyncio
async def test_paging_newest_first(client, world):
    await login(client, world["counselor"].email)
    for n in range(3):
        assert (await client.post(url(world["student"].id), json={"body": f"note {n}"})).status_code == 201
    data = (await client.get(url(world["student"].id), params={"limit": 2})).json()
    assert data["total"] == 3 and data["limit"] == 2 and [i["body"] for i in data["items"]] == ["note 2", "note 1"]
    data = (await client.get(url(world["student"].id), params={"limit": 2, "offset": 2})).json()
    assert [i["body"] for i in data["items"]] == ["note 0"]
    assert (await client.get(url(world["student"].id), params={"limit": 51})).status_code == 422


@pytest.mark.asyncio
async def test_students_section_links_each_student_to_notes(client, db_session, world):
    agency_app = await mk_application(db_session, university=world["university"], counselor=world["counselor"])  # bridged: no login
    for email, role in ((world["counselor"].email, "counselor"), (world["admin"].email, "admin")):
        await login(client, email)
        data = (await client.get(PORTAL.format(role, "students"))).json()
        assert {"key": "notes", "label": "", "type": "student_notes"} in data["columns"]
        rows = {row["id"]: row for row in data["rows"]}
        base = "/overseas/counselor" if role == "counselor" else "/overseas/admin"
        assert rows[str(world["own"].id)]["notes"] == f"{base}/students/{world['student'].id}/notes"
        assert rows[str(agency_app.id)]["notes"] is None
    data = (await client.get(PORTAL.format("admin", "applications"))).json()
    assert "notes" not in {c["key"] for c in data["columns"]}  # only the Students section


@pytest.mark.asyncio
async def test_admin_users_directory_links_overseas_students_only(client, db_session, world):
    await login(client, world["admin"].email)
    data = (await client.get(PORTAL.format("admin", "users"))).json()
    assert {"key": "notes", "label": "", "type": "student_notes"} in data["columns"]
    rows = {row["id"]: row for row in data["rows"]}
    assert rows[str(world["student"].id)]["notes"] == f"/overseas/admin/students/{world['student'].id}/notes"
    assert rows[str(world["counselor"].id)]["notes"] is None
