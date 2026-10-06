"""bdm-020 (DEC-SCOPE-087, spec §2) -- a linked School's student development counts for the BDM side, read through the School
module's own analytics (AC1), with Student Profile Completion "not tracked" (AC2, A2) and never a student row (AC3)."""

from uuid import UUID, uuid4

import pytest

from app.models import (
    OverseasApplication,
    SchoolCareerRecord,
    SchoolLanguageRecord,
    SchoolPsychometricRecord,
    SchoolStudent,
    SchoolTestPrepRecord,
)
from tests.agn003_helpers import mk_university
from tests.bdm001_helpers import login, make_user
from tests.bdm002_helpers import ORGS
from tests.bdm005_helpers import world
from tests.bdm018_helpers import SCHOOLS, pending_request, school_payload, school_world, user

DEVELOPMENT = "/api/v1/school/analytics/student-development"
TRACKED = ("career_guidance", "psychometric_test", "foreign_language", "english_testing", "university_guidance")


def url(org_id: str) -> str:
    return f"{ORGS}/{org_id}/school-activity"


async def _linked(client, db) -> dict:
    w = await pending_request(client, db)
    response = await client.post(SCHOOLS, json=school_payload(bdm_onboarding_request_id=w["item"]["id"]))
    assert response.status_code == 201, response.text
    w["school"] = response.json()
    await login(client, await user(db, w["ids"]["owner"]))
    return w


async def _student(db, school_id: str, admin_id) -> SchoolStudent:
    student = SchoolStudent(school_id=UUID(school_id), student_code=uuid4().hex[:8].upper(), full_name="Priya Student", created_by_user_id=admin_id)
    db.add(student)
    await db.commit()
    return student


async def _seed(db, w) -> None:
    """Three students: one with every activity completed, one with only started/scheduled records, one with nothing."""
    admin = w["ids"]["admin"]
    done, started, _idle = [(await _student(db, w["school"]["id"], admin)).id for _ in range(3)]
    counselor = (await make_user(db, "career_counselor", "overseas")).id
    team = (await make_user(db, "psychometric_team", "overseas")).id
    academic = (await make_user(db, "academic_team", "overseas")).id
    university = (await mk_university(db)).id
    db.add_all(
        [
            SchoolCareerRecord(school_student_id=done, career_counselor_user_id=counselor, record_type="guidance_session", notes="x", status="completed"),
            SchoolCareerRecord(school_student_id=started, career_counselor_user_id=counselor, record_type="guidance_session", notes="x", status="scheduled"),
            SchoolPsychometricRecord(school_student_id=done, psychometric_team_user_id=team, assessment_type="Aptitude", status="completed"),
            SchoolPsychometricRecord(school_student_id=started, psychometric_team_user_id=team, assessment_type="Aptitude", status="assigned"),
            SchoolLanguageRecord(school_student_id=done, academic_team_user_id=academic, language="German", certification_status="certified"),
            SchoolLanguageRecord(school_student_id=started, academic_team_user_id=academic, language="French"),
            SchoolTestPrepRecord(school_student_id=done, academic_team_user_id=academic, test_type="ielts", status="completed"),
            SchoolTestPrepRecord(school_student_id=started, academic_team_user_id=academic, test_type="ielts"),
            OverseasApplication(school_student_id=done, university_id=university, intake="Fall 2027", status="university_selection"),
            OverseasApplication(school_student_id=started, university_id=university, intake="Fall 2027", status="enquiry"),
        ]
    )
    await db.commit()


async def _school_module_view(client, db, school_id: str) -> dict:
    coordinator = await make_user(db, "school_coordinator", "overseas")
    coordinator.profile = {"school_id": school_id}
    await db.commit()
    await login(client, coordinator)
    response = await client.get(DEVELOPMENT)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_counts_equal_the_school_modules_own_student_development(client, db_session):
    w = await _linked(client, db_session)
    await _seed(db_session, w)
    response = await client.get(url(w["org"]["id"]))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["linked"] is True
    assert body["school"] == {"name": w["school"]["name"], "school_code": w["school"]["school_code"]}
    assert body["total_students"] == 3
    tracked = {m["key"]: (m["completed"], m["pending"]) for m in body["metrics"] if m["tracked"]}
    assert tracked == {key: (1, 2) for key in TRACKED}

    school = await _school_module_view(client, db_session, w["school"]["id"])  # AC1: the School's own page, same figures
    assert body["total_students"] == school["headcounts"]["students"]
    assert tracked == {a["key"]: (a["completed"], a["pending"]) for a in school["activities"]}
    assert [m["label"] for m in body["metrics"][:5]] == [a["label"] for a in school["activities"]]


@pytest.mark.asyncio
async def test_student_profile_completion_is_listed_as_not_tracked(client, db_session):
    w = await _linked(client, db_session)
    metrics = (await client.get(url(w["org"]["id"]))).json()["metrics"]
    assert [m["key"] for m in metrics] == [*TRACKED, "student_profile_completion"]
    assert metrics[-1] == {"key": "student_profile_completion", "label": "Student Profile Completion", "tracked": False, "completed": None, "pending": None}
    assert all(m["completed"] == 0 and m["pending"] == 0 for m in metrics[:5])  # a new School: every tracked count is a real 0


@pytest.mark.asyncio
async def test_an_unlinked_school_organization_is_not_onboarded_yet(client, db_session):
    w = await school_world(client, db_session)
    response = await client.get(url(w["org"]["id"]))
    assert response.status_code == 200, response.text
    assert response.json() == {"linked": False, "school": None, "total_students": None, "metrics": []}


@pytest.mark.asyncio
async def test_no_student_row_or_identifier_is_ever_returned(client, db_session):
    w = await _linked(client, db_session)
    await _seed(db_session, w)
    text = (await client.get(url(w["org"]["id"]))).text
    assert "Priya" not in text
    assert "school_student_id" not in text and "student_code" not in text
    body = (await client.get(url(w["org"]["id"]))).json()
    assert set(body) == {"linked", "school", "total_students", "metrics"}
    assert all(set(m) == {"key", "label", "tracked", "completed", "pending"} for m in body["metrics"])


@pytest.mark.asyncio
async def test_a_student_who_transferred_out_counts_at_the_new_school_only(client, db_session):
    w = await _linked(client, db_session)
    await _seed(db_session, w)
    w2 = await _linked(client, db_session)
    moved_id = (await _student(db_session, w["school"]["id"], w["ids"]["admin"])).id
    (await db_session.get_one(SchoolStudent, moved_id)).school_id = UUID(w2["school"]["id"])  # ENH-005: the current school
    await db_session.commit()
    await login(client, await user(db_session, w["ids"]["owner"]))
    assert (await client.get(url(w["org"]["id"]))).json()["total_students"] == 3
    await login(client, await user(db_session, w2["ids"]["owner"]))
    assert (await client.get(url(w2["org"]["id"]))).json()["total_students"] == 1


@pytest.mark.asyncio
async def test_scope_follows_the_organization_and_other_roles_are_refused(client, db_session):
    w = await _linked(client, db_session)
    org_id = w["org"]["id"]
    for name in ("peer", "manager", "super_admin"):  # module scope, own team, everything
        await login(client, await user(db_session, w["ids"][name]))
        assert (await client.get(url(org_id))).status_code == 200, name
    for name in ("other_type", "other_manager"):  # outside the module / team: indistinguishable from unknown
        await login(client, await user(db_session, w["ids"][name]))
        response = await client.get(url(org_id))
        assert (response.status_code, response.json()["detail"]) == (404, "Organization not found"), name
    assert (await client.get(url(str(uuid4())))).status_code == 404
    for name in ("it_admin", "student"):
        await login(client, await user(db_session, w["ids"][name]))
        assert (await client.get(url(org_id))).status_code == 403, name
    coordinator = await make_user(db_session, "school_coordinator", "overseas")
    coordinator.profile = {"school_id": w["school"]["id"]}
    await db_session.commit()
    await login(client, coordinator)
    assert (await client.get(url(org_id))).status_code == 403


@pytest.mark.asyncio
async def test_a_non_school_organization_has_no_school_activity(client, db_session):
    w = await world(client, db_session, "college")
    await login(client, await user(db_session, w["ids"]["manager"]))
    response = await client.get(url(w["org"]["id"]))
    assert (response.status_code, response.json()["detail"]) == (404, "School activity is only for School organizations")
