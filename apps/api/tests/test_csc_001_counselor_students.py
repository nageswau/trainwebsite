"""csc-001 (DEC-SCOPE-226) -- a counselor's students are their own applications' students plus the students linked to them
(`overseas_student_counselors`). The picker (GET /lookups/overseas-students) and the write it feeds (POST /workflows/overseas/appointments)
use the same scope (ENH-031 §5); application-based behaviour is unchanged (test_enh_031_lookups_students, test_cns_001_counselor_workspace)."""

import pytest

from app.models import OverseasStudentCounselor
from tests.agn001_helpers import login, mk_user, uniq
from tests.enh031_helpers import mk_application, mk_university

LOOKUP = "/api/v1/lookups/overseas-students"
APPOINTMENTS = "/api/v1/workflows/overseas/appointments"


async def link(db, student, counselor) -> None:
    db.add(OverseasStudentCounselor(student_user_id=student.id, counselor_user_id=counselor.id, assigned_by_user_id=counselor.id))
    await db.commit()


def ids(response) -> list[str]:
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["items"]]


def booking(student) -> dict:
    return {"student_id": str(student.id), "scheduled_at": "2027-01-15T10:00:00", "appointment_type": "Career Counseling"}


@pytest.mark.asyncio
async def test_a_linked_student_with_no_application_is_in_the_counselors_picker(client, db_session):
    tag = uniq("c01")
    linked = await mk_user(db_session, role="overseas_student", full_name=f"{tag} Linked")
    await mk_user(db_session, role="overseas_student", full_name=f"{tag} Stranger")
    counselor = await mk_user(db_session, role="counselor")
    await link(db_session, linked, counselor)
    await login(client, counselor.email)
    assert ids(await client.get(LOOKUP, params={"q": tag})) == [str(linked.id)]


@pytest.mark.asyncio
async def test_linked_and_application_students_are_listed_once_each(client, db_session):
    tag = uniq("c01")
    both = await mk_user(db_session, role="overseas_student", full_name=f"{tag} A Both")
    app_only = await mk_user(db_session, role="overseas_student", full_name=f"{tag} B Application")
    counselor = await mk_user(db_session, role="counselor")
    university = await mk_university(db_session)
    await link(db_session, both, counselor)
    await mk_application(db_session, student=both, university=university, counselor=counselor)
    await mk_application(db_session, student=app_only, university=university, counselor=counselor)
    await login(client, counselor.email)
    assert ids(await client.get(LOOKUP, params={"q": tag})) == [str(both.id), str(app_only.id)]


@pytest.mark.asyncio
async def test_another_counselors_linked_student_is_not_visible(client, db_session):
    tag = uniq("c01")
    theirs = await mk_user(db_session, role="overseas_student", full_name=f"{tag} Theirs")
    me = await mk_user(db_session, role="counselor")
    other = await mk_user(db_session, role="counselor")
    await link(db_session, theirs, other)
    await login(client, me.email)
    assert ids(await client.get(LOOKUP, params={"q": tag})) == []


@pytest.mark.asyncio
async def test_q_still_filters_linked_students(client, db_session):
    tag = uniq("c01")
    alpha = await mk_user(db_session, role="overseas_student", full_name=f"{tag} Alpha")
    beta = await mk_user(db_session, role="overseas_student", full_name=f"{tag} Beta")
    counselor = await mk_user(db_session, role="counselor")
    await link(db_session, alpha, counselor)
    await link(db_session, beta, counselor)
    await login(client, counselor.email)
    assert ids(await client.get(LOOKUP, params={"q": f"{tag} Beta"})) == [str(beta.id)]


@pytest.mark.asyncio
async def test_an_it_counselor_is_still_refused(client, db_session):
    counselor = await mk_user(db_session, role="counselor", division="it")
    await login(client, counselor.email, division="it")
    assert (await client.get(LOOKUP)).status_code == 403


@pytest.mark.asyncio
async def test_the_counselor_books_an_appointment_for_a_linked_student(client, db_session):
    student = await mk_user(db_session, role="overseas_student")
    counselor = await mk_user(db_session, role="counselor")
    await link(db_session, student, counselor)
    await login(client, counselor.email)
    response = await client.post(APPOINTMENTS, json=booking(student))
    assert response.status_code == 201, response.text


@pytest.mark.asyncio
async def test_the_counselor_cannot_book_for_another_counselors_linked_student(client, db_session):
    student = await mk_user(db_session, role="overseas_student")
    me = await mk_user(db_session, role="counselor")
    other = await mk_user(db_session, role="counselor")
    await link(db_session, student, other)
    await login(client, me.email)
    response = await client.post(APPOINTMENTS, json=booking(student))
    assert response.status_code == 403
    assert response.json()["detail"] == "Student is outside your assigned scope"


@pytest.mark.asyncio
async def test_the_counselors_appointment_list_shows_a_linked_students_booking(client, db_session):
    """QA-01: the booking the counselor makes for a linked student shows in their Student appointments list."""
    student = await mk_user(db_session, role="overseas_student")
    theirs = await mk_user(db_session, role="overseas_student")
    me = await mk_user(db_session, role="counselor")
    other = await mk_user(db_session, role="counselor")
    await link(db_session, student, me)
    await link(db_session, theirs, other)
    await login(client, other.email)
    assert (await client.post(APPOINTMENTS, json=booking(theirs))).status_code == 201
    await login(client, me.email)
    assert (await client.post(APPOINTMENTS, json=booking(student))).status_code == 201
    response = await client.get("/api/v1/portal/overseas/counselor/appointments")
    assert response.status_code == 200, response.text
    assert [row["student_id"] for row in response.json()["rows"]] == [str(student.id)]
