"""nehn-039 -- school-side document statuses (docs/superpowers/specs/2026-10-27-nehn-039-school-document-statuses-design.md, D1-D7)."""

import uuid

import pytest
import pytest_asyncio
from enh005_helpers import login, mk_school, mk_staff, mk_user, move_student_directly
from enh016_helpers import make_university
from sqlalchemy import func, select

from app.models import ApplicationChecklist, ApplicationChecklistItem, AuditLog, OverseasApplication, SchoolParentLink

AUDIT = "school.document_statuses_view"
NOT_FOUND = "Student not found"


def url(student_id) -> str:
    return f"/api/v1/school/students/{student_id}/document-statuses"


async def bridge(db, student, *, items=None, university=None) -> OverseasApplication:
    """A School-bridged application; `items` (document_type, label, required, mark, sensitivity) makes a checklist for it."""
    university = university or await make_university(db)
    application = OverseasApplication(student_id=None, school_student_id=student.id, university_id=university.id, intake="Fall 2027", status="documentation")
    db.add(application)
    await db.flush()
    if items is not None:
        db.add(ApplicationChecklist(application_id=application.id, gate_mode="warn"))
        await db.flush()
        for position, (document_type, label, required, mark, sensitivity) in enumerate(items, start=1):
            db.add(
                ApplicationChecklistItem(
                    application_id=application.id,
                    position=position,
                    document_type=document_type,
                    label=label,
                    required=required,
                    allowed_statuses=[],
                    notes="private counselor note",
                    mark=mark,
                    sensitivity=sensitivity,
                )
            )
    await db.commit()
    return application


STANDARD_ITEMS = [
    ("Passport", None, True, "not_required", "identity"),
    ("Transcripts", "Grade 12 transcript", True, None, "standard"),
    ("Financial documents", "Bank statement", True, "requested", "financial"),
    ("Other", "Sponsor letter", False, None, "standard"),  # the type check catches a financial label on a standard item (D3)
    ("English test", None, False, "requested", "standard"),
]


@pytest_asyncio.fixture
async def world(db_session):
    ctx = await mk_school(db_session, label="N039", students=2)
    ctx["application"] = await bridge(db_session, ctx["students"][0], items=STANDARD_ITEMS)
    ctx["sid"] = str(ctx["students"][0].id)
    return ctx


@pytest.mark.parametrize("who", ["coordinator", "principal", "teacher", "parent"])
@pytest.mark.asyncio
async def test_school_readers_see_allowed_statuses(client, world, who):  # AC1, D2-D4
    await login(client, world[who].email)
    r = await client.get(url(world["sid"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["student_id"] == world["sid"]
    [application] = body["applications"]
    assert application == {
        "application_id": str(world["application"].id),
        "university_name": "U",
        "has_checklist": True,
        "items": [
            {"name": "Passport", "required": True, "status": "not_required", "status_label": "Not required"},
            {"name": "Grade 12 transcript", "required": True, "status": "missing", "status_label": "Missing"},
            {"name": "English test", "required": False, "status": "requested", "status_label": "Requested"},
        ],
    }


@pytest.mark.asyncio
async def test_no_files_notes_or_financial_words_leak(client, world):  # D2, D3
    await login(client, world["coordinator"].email)
    text = (await client.get(url(world["sid"]))).text
    for leaked in ("private counselor note", "Bank statement", "Sponsor", "Financial", "file_url", "document_id", "notes", "intake", "Fall 2027"):
        assert leaked not in text


@pytest.mark.asyncio
async def test_other_school_student_is_404(client, world, db_session):  # AC2
    other = await mk_school(db_session, label="N039-Other", students=1)
    await bridge(db_session, other["students"][0], items=STANDARD_ITEMS)
    await login(client, world["coordinator"].email)
    r = await client.get(url(other["students"][0].id))
    assert (r.status_code, r.json()["detail"]) == (404, NOT_FOUND)


@pytest.mark.parametrize("who", ["teacher", "parent"])
@pytest.mark.asyncio
async def test_unassigned_or_unlinked_student_is_404(client, world, who):  # D4: a parent sees only their child
    await login(client, world[who].email)
    r = await client.get(url(world["students"][1].id))
    assert (r.status_code, r.json()["detail"]) == (404, NOT_FOUND)


@pytest.mark.asyncio
async def test_unknown_student_is_404(client, world):
    await login(client, world["principal"].email)
    assert (await client.get(url(uuid.uuid4()))).status_code == 404


@pytest.mark.parametrize("role", ["career_counselor", "academic_team", "overseas_admin"])
@pytest.mark.asyncio
async def test_non_school_roles_are_403(client, world, db_session, role):  # D4
    member = await mk_staff(db_session, world["school"], world["admin"], role=role) if role != "overseas_admin" else world["admin"]
    await login(client, member.email)
    r = await client.get(url(world["sid"]))
    assert (r.status_code, r.json()["detail"]) == (403, "School role required")


@pytest.mark.asyncio
async def test_transferred_student_follows_the_current_school(client, world, db_session):  # edge case: transfers
    new_school = await mk_school(db_session, label="N039-New", students=0)
    await move_student_directly(db_session, world["students"][0], new_school["school"])
    await login(client, world["coordinator"].email)
    assert (await client.get(url(world["sid"]))).status_code == 404
    await login(client, new_school["coordinator"].email)
    r = await client.get(url(world["sid"]))
    assert r.status_code == 200
    assert len(r.json()["applications"][0]["items"]) == 3


@pytest.mark.asyncio
async def test_no_checklist_and_no_application_shapes(client, world, db_session):
    second = world["students"][1]
    await login(client, world["coordinator"].email)
    assert (await client.get(url(second.id))).json() == {"student_id": str(second.id), "applications": []}
    application = await bridge(db_session, second)
    [row] = (await client.get(url(second.id))).json()["applications"]
    assert row == {"application_id": str(application.id), "university_name": "U", "has_checklist": False, "items": []}


@pytest.mark.asyncio
async def test_applications_are_newest_first(client, world, db_session):
    newer = await bridge(db_session, world["students"][0], items=[])
    await login(client, world["coordinator"].email)
    ids = [a["application_id"] for a in (await client.get(url(world["sid"]))).json()["applications"]]
    assert ids == [str(newer.id), str(world["application"].id)]


@pytest.mark.asyncio
async def test_each_read_is_audited_without_contents(client, world, db_session):  # D6
    await login(client, world["principal"].email)
    assert (await client.get(url(world["sid"]))).status_code == 200
    row = await db_session.scalar(select(AuditLog).where(AuditLog.action == AUDIT, AuditLog.user_id == world["principal"].id))
    assert (row.entity_type, row.entity_id) == ("school_student", world["sid"])
    assert row.metadata_json == {"school_id": str(world["school"].id), "applications": 1, "items": 3}


@pytest.mark.asyncio
async def test_a_refused_read_writes_no_view_audit(client, world, db_session):
    await login(client, world["parent"].email)
    assert (await client.get(url(world["students"][1].id))).status_code == 404
    count = await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == AUDIT, AuditLog.user_id == world["parent"].id))
    assert count == 0


@pytest.mark.asyncio
async def test_a_second_childs_parent_link_is_independent(client, world, db_session):
    """A parent with no school_id in their profile still reads a linked child (ENH-008 scoping)."""
    parent = await mk_user(db_session, role="school_parent", name="Unschooled parent")
    db_session.add(SchoolParentLink(parent_user_id=parent.id, school_student_id=world["students"][0].id, linked_by_user_id=world["coordinator"].id))
    await db_session.commit()
    await login(client, parent.email)
    assert (await client.get(url(world["sid"]))).status_code == 200
