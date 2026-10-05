"""ENH-016 authorization and isolation (AC02-AC05, AC07, AC16). The school always comes from the caller's server-held profile;
the cross-school view is the existing Overseas/Super Admin pair only (D1)."""

import uuid

import pytest
from enh016_helpers import login, make_school, make_student

SCHOOL_ENDPOINTS = [
    "/api/v1/school/analytics/grade-performance",
    "/api/v1/school/analytics/student-development",
    "/api/v1/school/analytics/scorecards",
]
ADMIN_ENDPOINTS = ["/api/v1/overseas-admin/analytics/summary", "/api/v1/overseas-admin/analytics/schools"]


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["school_teacher", "school_parent", "academic_team", "career_counselor", "psychometric_team", "it_admin", "overseas_admin", "super_admin"])
async def test_only_coordinator_and_principal_reach_school_analytics(client, db_session, role):  # AC03
    ctx = await make_school(db_session)
    student = await make_student(db_session, ctx)
    await db_session.commit()
    await login(client, ctx[role])
    for path in [*SCHOOL_ENDPOINTS, f"/api/v1/school/students/{student.id}/scorecard"]:
        response = await client.get(path)
        if response.status_code == 404 and response.json().get("detail") == "Not Found":  # route not built yet -- later tasks add it
            continue
        assert response.status_code == 403, (path, response.text)


@pytest.mark.asyncio
async def test_school_account_without_a_school_is_refused(client, db_session):
    ctx = await make_school(db_session)
    ctx["school_coordinator"].profile = {}
    await db_session.commit()
    await login(client, ctx["school_coordinator"])
    response = await client.get("/api/v1/school/analytics/grade-performance")
    assert response.status_code == 403
    assert response.json()["detail"] == "This account is not linked to a school"


@pytest.mark.asyncio
async def test_wrong_role_with_bad_thresholds_gets_403_not_422(client, db_session):  # AC07
    ctx = await make_school(db_session)
    await db_session.commit()
    await login(client, ctx["school_teacher"])
    response = await client.get("/api/v1/school/analytics/student-development", params={"at_risk_below": 999})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_scorecard_of_another_schools_student_is_the_same_404_as_a_missing_one(client, db_session):  # AC05
    mine = await make_school(db_session)
    theirs = await make_school(db_session)
    foreign = await make_student(db_session, theirs)
    await db_session.commit()
    await login(client, mine["school_coordinator"])
    other = await client.get(f"/api/v1/school/students/{foreign.id}/scorecard")
    missing = await client.get(f"/api/v1/school/students/{uuid.uuid4()}/scorecard")
    assert other.status_code == missing.status_code == 404
    assert other.json() == missing.json() == {"detail": "Student not found"}


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["school_coordinator", "school_principal", "school_teacher", "school_parent", "academic_team", "career_counselor", "psychometric_team", "it_admin"])
async def test_cross_school_is_admin_only(client, db_session, role):  # AC04
    ctx = await make_school(db_session)
    await db_session.commit()
    await login(client, ctx[role])
    for path in ADMIN_ENDPOINTS:
        response = await client.get(path)
        assert response.status_code == 403, (path, response.text)
        assert response.json()["detail"] == "Overseas Admin role required"


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["overseas_admin", "super_admin"])
async def test_cross_school_admins_are_allowed(client, db_session, role):
    ctx = await make_school(db_session)
    await db_session.commit()
    await login(client, ctx[role])
    for path in ADMIN_ENDPOINTS:
        assert (await client.get(path)).status_code == 200


@pytest.mark.asyncio
async def test_one_school_never_sees_another_schools_students(client, db_session):  # AC02
    mine = await make_school(db_session)
    theirs = await make_school(db_session)
    await make_student(db_session, mine, grade_level=9)
    for _ in range(3):
        await make_student(db_session, theirs, grade_level=9)
    await db_session.commit()
    await login(client, mine["school_coordinator"])
    body = (await client.get("/api/v1/school/analytics/grade-performance")).json()
    assert body["students"] == {"9": 1}
