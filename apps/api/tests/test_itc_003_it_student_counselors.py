"""itc-003 (DEC-SCOPE-337) -- the IT student -> counselor link (`it_student_counselors`, one counselor per student, Q-03): set on the
lead's student link, removed with a mistaken link, moved by the IT Admin with a reason (csc-005 / ccrm-033 rules), and read by the IT
counselor (only their own students; anything else is 404) and by the student (their own counselor's name)."""

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, ItStudentCounselor, Notification
from tests.bdm017_helpers import conversion
from tests.tel004_helpers import make_user
from tests.tel018_helpers import as_user, c_url, handover, make_counselor, make_student, setup

MINE = "/api/v1/counselor/it/students"
PICKER = "/api/v1/lookups/it-counselors"


def assign_url(student_id) -> str:
    return f"/api/v1/admin/it/students/{student_id}/counselor"


async def linked(db, student):
    return await db.scalar(select(ItStudentCounselor.counselor_user_id).where(ItStudentCounselor.student_user_id == student.id).execution_options(populate_existing=True))


async def link_row(db, student, counselor, by=None) -> None:
    db.add(ItStudentCounselor(student_user_id=student.id, counselor_user_id=counselor.id, assigned_by_user_id=(by or counselor).id))
    await db.commit()


async def notes(db, user, title: str) -> int:
    return await db.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == user.id, Notification.title == title))


async def handed_over(client, db, division="it"):
    _, tel, counselor, lead = await setup(db, division, status="counselling_completed")
    assert (await handover(client, tel, lead, counselor)).status_code == 200
    await as_user(client, counselor)
    return counselor, lead


# --- AC1: the link sets the counselor ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_counselors_student_link_makes_them_the_students_counselor(client, db_session):
    counselor, lead = await handed_over(client, db_session)
    student = await make_student(db_session)
    response = await client.post(c_url(lead.id, "/student-link"), json={"student_id": str(student.id)})
    assert response.status_code == 200, response.text
    assert await linked(db_session, student) == counselor.id
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "it.student.counselor_link", AuditLog.entity_id == str(student.id)))
    assert (audit.user_id, audit.metadata_json) == (counselor.id, {"counselor_id": str(counselor.id), "lead_id": str(lead.id)})
    body = (await client.get(MINE)).json()
    assert [i["id"] for i in body["items"]] == [str(student.id)] and body["total"] == 1
    assert (await client.get(f"{MINE}/{student.id}")).json()["full_name"] == student.full_name


@pytest.mark.asyncio
async def test_the_admin_link_sets_the_leads_counselor_and_an_existing_counselor_is_kept(client, db_session):
    admin = await make_user(db_session, "it_admin", "it")
    _, _, counselor, lead = await setup(db_session, status="counselling_completed")
    lead.owner_id = counselor.id
    student = await make_student(db_session)
    await as_user(client, admin)
    assert (await client.post(conversion(lead.id), json={"student_email": student.email})).status_code == 200
    assert await linked(db_session, student) == counselor.id

    _, _, other, second = await setup(db_session, status="counselling_completed")  # one counselor per student: kept, the admin reassigns
    second.owner_id = other.id
    kept = await make_student(db_session)
    await link_row(db_session, kept, counselor, admin)
    assert (await client.post(conversion(second.id), json={"student_email": kept.email})).status_code == 200
    assert await linked(db_session, kept) == counselor.id


@pytest.mark.asyncio
async def test_an_unowned_or_overseas_lead_sets_no_it_counselor(client, db_session):
    admin = await make_user(db_session, "it_admin", "it")
    _, _, _, lead = await setup(db_session, status="counselling_completed")  # no owner
    student = await make_student(db_session)
    await as_user(client, admin)
    assert (await client.post(conversion(lead.id), json={"student_email": student.email})).status_code == 200
    assert await linked(db_session, student) is None

    _, lead = await handed_over(client, db_session, "overseas")
    ov_student = await make_student(db_session, "overseas")
    assert (await client.post(c_url(lead.id, "/student-link"), json={"student_id": str(ov_student.id)})).status_code == 200
    assert await linked(db_session, ov_student) is None


@pytest.mark.asyncio
async def test_unlinking_a_mistaken_student_removes_the_counselor_link_it_made(client, db_session):
    counselor, lead = await handed_over(client, db_session)
    student = await make_student(db_session)
    await client.post(c_url(lead.id, "/student-link"), json={"student_id": str(student.id)})
    assert (await client.delete(c_url(lead.id, "/student-link"))).status_code == 200
    assert await linked(db_session, student) is None
    assert (await client.get(f"{MINE}/{student.id}")).status_code == 404


@pytest.mark.asyncio
async def test_unlinking_keeps_a_link_the_admin_has_moved(client, db_session):
    admin = await make_user(db_session, "it_admin", "it")
    other = await make_counselor(db_session)
    counselor, lead = await handed_over(client, db_session)
    student = await make_student(db_session)
    await client.post(c_url(lead.id, "/student-link"), json={"student_id": str(student.id)})
    await as_user(client, admin)
    assert (await client.put(assign_url(student.id), json={"counselor_id": str(other.id), "reason": "Workload"})).status_code == 200
    await as_user(client, counselor)
    assert (await client.delete(c_url(lead.id, "/student-link"))).status_code == 200
    assert await linked(db_session, student) == other.id


# --- AC2: the reassignment --------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_it_admin_moves_a_student_and_both_counselors_are_told(client, db_session):
    """The backlog's + case: S moves from C1 to C2; C2 sees S and C1 no longer does (AC2, AC3)."""
    admin = await make_user(db_session, "it_admin", "it")
    c1, c2 = await make_counselor(db_session), await make_counselor(db_session)
    student = await make_student(db_session)
    await link_row(db_session, student, c1)
    await as_user(client, admin)
    response = await client.put(assign_url(student.id), json={"counselor_id": str(c2.id), "reason": "Student request"})
    assert response.status_code == 200, response.text
    assert response.json() == {"id": str(student.id), "counselor_id": str(c2.id), "counselor_name": c2.full_name, "changed": True}
    assert await linked(db_session, student) == c2.id
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "it.student.counselor_assign", AuditLog.entity_id == str(student.id)))
    assert audit.user_id == admin.id and audit.metadata_json == {"from_counselor_id": str(c1.id), "to_counselor_id": str(c2.id), "reason": "Student request"}
    assert await notes(db_session, c2, "Student assigned to you") == 1 and await notes(db_session, c1, "Student reassigned") == 1
    note = await db_session.scalar(select(Notification).where(Notification.user_id == c2.id))
    assert note.body.endswith("Reason: Student request") and note.action_url == "/it/counselor/students"

    await as_user(client, c2)
    assert (await client.get(f"{MINE}/{student.id}")).status_code == 200
    await as_user(client, c1)
    assert (await client.get(f"{MINE}/{student.id}")).status_code == 404  # AC3
    assert str(student.id) not in [i["id"] for i in (await client.get(MINE)).json()["items"]]


@pytest.mark.asyncio
async def test_a_first_assignment_needs_no_reason_and_the_same_counselor_changes_nothing(client, db_session):
    admin = await make_user(db_session, "it_admin", "it")
    counselor = await make_counselor(db_session)
    student = await make_student(db_session)
    await as_user(client, admin)
    assert (await client.put(assign_url(student.id), json={"counselor_id": str(counselor.id)})).json()["changed"] is True
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "it.student.counselor_assign", AuditLog.entity_id == str(student.id)))
    assert audit.metadata_json == {"from_counselor_id": None, "to_counselor_id": str(counselor.id)}
    again = await client.put(assign_url(student.id), json={"counselor_id": str(counselor.id)})
    assert (again.status_code, again.json()["changed"]) == (200, False)
    assert await notes(db_session, counselor, "Student assigned to you") == 1


@pytest.mark.asyncio
async def test_the_reassignment_refuses_bad_input(client, db_session):
    admin = await make_user(db_session, "it_admin", "it")
    c1, c2 = await make_counselor(db_session), await make_counselor(db_session)
    student = await make_student(db_session)
    await link_row(db_session, student, c1)
    await as_user(client, admin)
    missing_reason = await client.put(assign_url(student.id), json={"counselor_id": str(c2.id)})
    assert (missing_reason.status_code, missing_reason.json()["detail"]) == (422, "Give a reason for the reassignment")
    for bad in (await make_counselor(db_session, "overseas"), await make_counselor(db_session, active=False), admin):
        response = await client.put(assign_url(student.id), json={"counselor_id": str(bad.id), "reason": "x"})
        assert (response.status_code, response.json()["detail"]) == (422, "Choose an active IT counselor")
    overseas_student = await make_student(db_session, "overseas")
    assert (await client.put(assign_url(overseas_student.id), json={"counselor_id": str(c2.id)})).status_code == 404
    assert await linked(db_session, student) == c1.id


@pytest.mark.asyncio
async def test_only_the_it_admin_reassigns(client, db_session):
    """The backlog's − case: an overseas counselor (or anyone but the IT Admin) is 403."""
    c1 = await make_counselor(db_session)
    student = await make_student(db_session)
    for role, division in (("counselor", "overseas"), ("counselor", "it"), ("overseas_admin", "overseas"), ("it_student", "it")):
        await as_user(client, await make_user(db_session, role, division))
        response = await client.put(assign_url(student.id), json={"counselor_id": str(c1.id)})
        assert (response.status_code, response.json()["detail"]) == (403, "Only the IT Admin can assign a counselor")
    assert await linked(db_session, student) is None


# --- AC3: the counselor's reads ---------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_counselor_reads_only_their_students_and_others_are_refused(client, db_session):
    counselor = await make_counselor(db_session)
    mine, theirs = await make_student(db_session), await make_student(db_session)
    await link_row(db_session, mine, counselor)
    await link_row(db_session, theirs, await make_counselor(db_session))
    await as_user(client, counselor)
    body = (await client.get(MINE, params={"q": mine.email.upper()})).json()
    assert [i["id"] for i in body["items"]] == [str(mine.id)]
    assert set(body["items"][0]) == {"id", "student_code", "full_name", "email", "phone", "linked_since"}
    assert (await client.get(f"{MINE}/{theirs.id}")).status_code == 404
    assert (await client.get(MINE, params={"limit": 0})).status_code == 422
    for role, division in (("counselor", "overseas"), ("it_admin", "it"), ("it_student", "it")):
        await as_user(client, await make_user(db_session, role, division))
        assert (await client.get(MINE)).status_code == 403
        assert (await client.get(f"{MINE}/{mine.id}")).status_code == 403


@pytest.mark.asyncio
async def test_the_picker_lists_active_it_counselors_for_the_it_admin_only(client, db_session):
    active, inactive, overseas = await make_counselor(db_session), await make_counselor(db_session, active=False), await make_counselor(db_session, "overseas")
    await as_user(client, await make_user(db_session, "it_admin", "it"))
    ids = {i["id"] for i in (await client.get(PICKER, params={"limit": 50, "q": active.full_name})).json()["items"]}
    assert str(active.id) in ids and not {str(inactive.id), str(overseas.id)} & ids
    await as_user(client, await make_user(db_session, "overseas_admin", "overseas"))
    assert (await client.get(PICKER)).status_code == 403


# --- the portal pages -------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_portal_shows_the_counselor_to_admin_counselor_and_student(client, db_session):
    counselor = await make_counselor(db_session)
    student = await make_student(db_session)
    await link_row(db_session, student, counselor)

    await as_user(client, await make_user(db_session, "it_admin", "it"))
    admin_page = (await client.get("/api/v1/portal/it/admin/students")).json()
    assert {"key": "assign", "label": "", "type": "assign_it_student_counselor"} in admin_page["columns"]
    row = next(r for r in admin_page["rows"] if r["id"] == str(student.id))
    assert (row["counselor"], row["counselor_id"], row["assign"]) == (counselor.full_name, str(counselor.id), str(student.id))

    await as_user(client, counselor)
    mine = (await client.get("/api/v1/portal/it/counselor/students")).json()
    assert mine["title"] == "My Students" and [r["name"] for r in mine["rows"]] == [student.full_name]

    await as_user(client, student)
    tiles = {m["label"]: m["value"] for m in (await client.get("/api/v1/portal/it/student/dashboard")).json()["metrics"]}
    assert tiles["Your counselor"] == counselor.full_name
    await as_user(client, await make_student(db_session))
    tiles = {m["label"]: m["value"] for m in (await client.get("/api/v1/portal/it/student/dashboard")).json()["metrics"]}
    assert tiles["Your counselor"] == "Not assigned yet"
