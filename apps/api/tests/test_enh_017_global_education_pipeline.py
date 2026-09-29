"""ENH-017 School-visible Global Education pipeline (spec 2026-09-29; DEC-SCOPE-036). High-level stage only (§19)."""

import pytest
from enh016_helpers import _user, login, make_school

from app.models import OverseasApplication

URL = "/api/v1/school/global-education/pipeline"
TOP_KEYS = {"grade", "students_in_scope", "bridged_students", "funnel", "not_tracked", "students"}
FUNNEL_KEYS = ["pathway", "profile_evaluation", "shortlisted", "offer", "visa", "admitted"]


async def bridge(db, student, university, *, status="enquiry", **fields) -> OverseasApplication:
    application = OverseasApplication(student_id=None, school_student_id=student.id, university_id=university.id, intake="Fall 2027", status=status, **fields)
    db.add(application)
    await db.flush()
    return application


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["school_coordinator", "school_principal"])
async def test_coordinator_and_principal_read_their_own_school(client, db_session, role):  # AC01
    ctx = await make_school(db_session)
    await db_session.commit()
    await login(client, ctx[role])

    response = await client.get(URL)

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == TOP_KEYS
    assert [s["key"] for s in body["funnel"]] == FUNNEL_KEYS
    assert set(body["students"]) == {"items", "total", "limit", "offset"}


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["school_teacher", "school_parent", "academic_team", "career_counselor", "psychometric_team", "overseas_admin", "super_admin", "it_admin"])
async def test_every_other_role_is_refused(client, db_session, role):  # AC02
    ctx = await make_school(db_session)
    await db_session.commit()
    await login(client, ctx[role])
    assert (await client.get(URL)).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["counselor", "overseas_student"])
async def test_overseas_counselor_and_student_are_refused(client, db_session, role):  # AC02
    user = _user(role, "overseas")
    db_session.add(user)
    await db_session.commit()
    await login(client, user)
    assert (await client.get(URL)).status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_is_401(client):  # AC02
    assert (await client.get(URL)).status_code == 401


@pytest.mark.asyncio
async def test_coordinator_without_a_linked_school_is_403(client, db_session):  # AC03
    user = _user("school_coordinator", "overseas")  # profile {} -- no school_id
    db_session.add(user)
    await db_session.commit()
    await login(client, user)
    assert (await client.get(URL)).status_code == 403
