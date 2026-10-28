"""ccrm-046 (DEC-SCOPE-324) -- the overseas counselor creates any number of applications for a student in their caseload, from the
student 360. The shared create route now refuses a student outside the caseload (403, before the archive guard), and a counselor's
application is always their own and direct: another counselor or an agent in the body is 403. Student, admin and agent paths unchanged."""

import re

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import AuditLog, Notification, OverseasApplication, OverseasStudentArchive, OverseasStudentCounselor
from tests.agn001_helpers import login, mk_user, uniq
from tests.enh031_helpers import mk_application, mk_course, mk_university

CREATE = "/api/v1/workflows/overseas/applications"
PORTAL = "/api/v1/portal/overseas/{}/applications"
CODE = re.compile(r"^APP-\d{6}$")


@pytest_asyncio.fixture
async def world(db_session):
    counselor = await mk_user(db_session, role="counselor", full_name="Cara Counselor")
    other = await mk_user(db_session, role="counselor", full_name="Otto Counselor")
    admin = await mk_user(db_session, role="overseas_admin", full_name="Ada Admin")
    agent = await mk_user(db_session, role="agent", full_name="Agnes Agent")
    walk_in = await mk_user(db_session, role="overseas_student", full_name=f"{uniq('c46')} Walk-in")
    stranger = await mk_user(db_session, role="overseas_student", full_name=f"{uniq('c46')} Stranger")
    db_session.add(OverseasStudentCounselor(student_user_id=walk_in.id, counselor_user_id=counselor.id, assigned_by_user_id=counselor.id))
    await db_session.commit()
    unis = [await mk_university(db_session, name=uniq("C46 Uni")) for _ in range(3)]
    return {"counselor": counselor, "other": other, "admin": admin, "agent": agent, "walk_in": walk_in, "stranger": stranger, "unis": unis}


def body(student, university, **extra) -> dict:
    return {"student_id": str(student.id), "university_id": str(university.id), "intake": "Sep 2027"} | extra


@pytest.mark.asyncio
async def test_counselor_creates_three_applications_for_a_walk_in_student(client, db_session, world):  # AC1, AC2
    await login(client, world["counselor"].email)
    ids = []
    for uni in world["unis"]:
        response = await client.post(CREATE, json=body(world["walk_in"], uni))
        assert response.status_code == 201, response.text
        ids.append(response.json()["id"])
    rows = (await db_session.scalars(select(OverseasApplication).where(OverseasApplication.student_id == world["walk_in"].id))).all()
    assert {str(r.id) for r in rows} == set(ids)
    assert {r.counselor_id for r in rows} == {world["counselor"].id}
    assert {r.agent_id for r in rows} == {None}
    assert {r.status for r in rows} == {"enquiry"}
    assert all(CODE.match(r.application_code) for r in rows) and len({r.application_code for r in rows}) == 3
    audits = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "overseas.application.create", AuditLog.user_id == world["counselor"].id))).all()
    assert {a.entity_id for a in audits} >= set(ids)


@pytest.mark.asyncio
async def test_duplicate_open_application_is_409_but_another_course_and_a_withdrawn_one_are_allowed(client, db_session, world):  # AC3
    uni = world["unis"][0]
    course = await mk_course(db_session, uni, uniq("MSc"))
    await login(client, world["counselor"].email)
    first = await client.post(CREATE, json=body(world["walk_in"], uni))
    assert first.status_code == 201
    assert (await client.post(CREATE, json=body(world["walk_in"], uni))).status_code == 409
    assert (await client.post(CREATE, json=body(world["walk_in"], uni, course_id=str(course.id)))).status_code == 201
    row = await db_session.get(OverseasApplication, first.json()["id"])
    row.status = "withdrawn"
    await db_session.commit()
    assert (await client.post(CREATE, json=body(world["walk_in"], uni))).status_code == 201


@pytest.mark.asyncio
async def test_student_outside_the_caseload_is_403_even_when_archived(client, db_session, world):  # AC4
    await login(client, world["counselor"].email)
    response = await client.post(CREATE, json=body(world["stranger"], world["unis"][0]))
    assert response.status_code == 403 and response.json()["detail"] == "This student is not in your caseload"
    db_session.add(OverseasStudentArchive(student_user_id=world["stranger"].id, archived_by_user_id=world["admin"].id, reason="Studies finished"))
    await db_session.commit()
    assert (await client.post(CREATE, json=body(world["stranger"], world["unis"][0]))).status_code == 403  # no archive-state leak
    assert await db_session.scalar(select(OverseasApplication.id).where(OverseasApplication.student_id == world["stranger"].id)) is None


@pytest.mark.asyncio
async def test_a_student_counselled_on_an_application_is_in_the_caseload(client, db_session, world):
    await mk_application(db_session, student=world["stranger"], university=world["unis"][0], counselor=world["counselor"], status="rejected")
    await login(client, world["counselor"].email)
    assert (await client.post(CREATE, json=body(world["stranger"], world["unis"][1]))).status_code == 201
    await login(client, world["other"].email)
    assert (await client.post(CREATE, json=body(world["stranger"], world["unis"][2]))).status_code == 403


@pytest.mark.asyncio
async def test_archived_student_in_the_caseload_is_409(client, db_session, world):  # AC5
    db_session.add(OverseasStudentArchive(student_user_id=world["walk_in"].id, archived_by_user_id=world["counselor"].id, reason="Studies finished"))
    await db_session.commit()
    await login(client, world["counselor"].email)
    response = await client.post(CREATE, json=body(world["walk_in"], world["unis"][0]))
    assert response.status_code == 409 and "archived" in response.json()["detail"]


@pytest.mark.asyncio
async def test_a_counselor_cannot_assign_another_counselor_or_an_agent(client, db_session, world):
    await login(client, world["counselor"].email)
    uni = world["unis"][0]
    for extra in ({"counselor_id": str(world["other"].id)}, {"agent_id": str(world["agent"].id)}):
        response = await client.post(CREATE, json=body(world["walk_in"], uni, **extra))
        assert response.status_code == 403, extra
    assert await db_session.scalar(select(OverseasApplication.id).where(OverseasApplication.student_id == world["walk_in"].id)) is None
    named_self = await client.post(CREATE, json=body(world["walk_in"], uni, counselor_id=str(world["counselor"].id)))
    assert named_self.status_code == 201, named_self.text


@pytest.mark.asyncio
async def test_new_applications_reach_the_student_portal_and_the_counselor_portal(client, db_session, world):  # AC6
    await login(client, world["counselor"].email)
    created = {(await client.post(CREATE, json=body(world["walk_in"], u))).json()["id"] for u in world["unis"][:2]}
    counselor_rows = (await client.get(PORTAL.format("counselor"))).json()["rows"]
    assert created <= {r["id"] for r in counselor_rows}
    await login(client, world["walk_in"].email)
    student_rows = (await client.get(PORTAL.format("student"))).json()["rows"]
    assert {r["id"] for r in student_rows} == created
    notices = (await db_session.scalars(select(Notification.title).where(Notification.user_id == world["walk_in"].id))).all()
    assert notices.count("Application created") == 2


@pytest.mark.asyncio
async def test_admin_path_is_unchanged(client, db_session, world):
    await login(client, world["admin"].email)
    response = await client.post(CREATE, json=body(world["stranger"], world["unis"][0], counselor_id=str(world["other"].id)))
    assert response.status_code == 201, response.text
    row = await db_session.get(OverseasApplication, response.json()["id"])
    assert row.counselor_id == world["other"].id
