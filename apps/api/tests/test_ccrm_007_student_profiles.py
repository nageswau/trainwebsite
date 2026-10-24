"""ccrm-007 (DEC-SCOPE-249, P1-P6) -- the structured overseas student profile: personal and passport details, qualifications, work
experience, study preferences and English tests. GET/PUT /counselor/students/{id}/profile (the counselor in csc-001 scope, the Overseas
Admin any overseas student), GET/PUT /overseas/me/profile (the student, P1: every field), and the agency's read-only view without the
passport (P2/P3). A save replaces the whole profile (P5); last write wins and each save is audited with field names only."""

import uuid
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models import AgentStudent, AuditLog, Country, OverseasStudentEnglishTest, OverseasStudentProfile, OverseasStudentQualification
from tests.agn001_helpers import login, mk_active_org, mk_user, uniq
from tests.enh031_helpers import mk_application, mk_university

ME = "/api/v1/overseas/me/profile"
AGENT = "/api/v1/workflows/overseas/agent/crm/students/{}/profile"


def url(student_id) -> str:
    return f"/api/v1/counselor/students/{student_id}/profile"


async def mk_country(db, name: str) -> Country:
    country = Country(slug=uniq("c").lower(), name=name, overview="", tuition="", living_expenses="", visa_process=[], work_opportunities="", post_study_work="", pr_opportunities="", faq=[])
    db.add(country)
    await db.commit()
    return country


@pytest_asyncio.fixture
async def world(db_session):
    counselor = await mk_user(db_session, role="counselor", full_name="Nora Counselor")
    other = await mk_user(db_session, role="counselor", full_name="Omar Counselor")
    admin = await mk_user(db_session, role="overseas_admin", full_name="Ada Admin")
    student = await mk_user(db_session, role="overseas_student", full_name=f"{uniq('p7')} Student")
    university = await mk_university(db_session, name=uniq("Profile Uni"))
    await mk_application(db_session, student=student, university=university, counselor=counselor)
    uk = await mk_country(db_session, uniq("Albion"))
    return {"counselor": counselor, "other": other, "admin": admin, "student": student, "uk": uk}


def full_body(country_id) -> dict:
    return {
        "date_of_birth": "2003-05-14",
        "nationality": " Indian ",
        "city": "Hyderabad",
        "state": "Telangana",
        "passport_number": "z1234567",
        "passport_expiry": "2031-01-31",
        "work_experience_months": 18,
        "work_experience_details": "Junior developer",
        "preferred_country_ids": [str(country_id)],
        "preferred_course": "MSc Computer Science",
        "preferred_level": "PG",
        "preferred_intake": "September 2027",
        "study_mode": "full_time",
        "budget_min": "1500000",
        "budget_max": "2500000",
        "budget_currency": "INR",
        "qualifications": [
            {"level": "class_12", "institution": "Narayana College", "board_university": "TSBIE", "year_completed": 2020, "score_type": "percentage", "score": "91.4"},
            {"level": "bachelor", "qualification_name": "B.Tech CSE", "institution": "JNTU", "board_university": "JNTUH", "year_completed": 2024, "score_type": "cgpa", "score": "8.2", "backlogs": 1},
        ],
        "english_tests": [{"test_type": "IELTS", "status": "taken", "overall_score": "7.5", "test_date": "2025-11-02", "valid_until": "2027-11-02"}],
    }


@pytest.mark.asyncio
async def test_counselor_saves_two_qualifications_and_an_ielts_score_and_the_student_sees_them(client, db_session, world):
    """The backlog acceptance: counselor saves, the student sees them, another counselor gets 404."""
    await login(client, world["counselor"].email)
    response = await client.put(url(world["student"].id), json=full_body(world["uk"].id))
    assert response.status_code == 200, response.text
    saved = response.json()["profile"]
    assert saved["exists"] is True and saved["nationality"] == "Indian" and saved["passport_number"] == "Z1234567"
    assert [q["level"] for q in saved["qualifications"]] == ["class_12", "bachelor"]
    assert saved["qualifications"][1]["backlogs"] == 1 and saved["qualifications"][1]["score"] == "8.20"
    assert saved["english_tests"][0] | {"expired": False} == saved["english_tests"][0] and saved["english_tests"][0]["overall_score"] == "7.5"
    assert saved["preferred_countries"] == [{"id": str(world["uk"].id), "name": world["uk"].name}]
    assert saved["updated_by_name"] == "Nora Counselor" and saved["updated_at"]

    await login(client, world["student"].email)
    mine = (await client.get(ME)).json()["profile"]
    assert [q["institution"] for q in mine["qualifications"]] == ["Narayana College", "JNTU"]
    assert mine["english_tests"][0]["test_type"] == "IELTS" and mine["passport_number"] == "Z1234567"

    await login(client, world["other"].email)
    assert (await client.get(url(world["student"].id))).status_code == 404
    assert (await client.put(url(world["student"].id), json=full_body(world["uk"].id))).status_code == 404


@pytest.mark.asyncio
async def test_an_empty_profile_reads_as_not_saved_yet(client, world):
    await login(client, world["counselor"].email)
    data = (await client.get(url(world["student"].id))).json()
    assert data["student"] == {"id": str(world["student"].id), "full_name": world["student"].full_name, "student_code": None}
    assert data["profile"]["exists"] is False and data["profile"]["qualifications"] == [] and data["profile"]["preferred_countries"] == []


@pytest.mark.asyncio
async def test_a_save_replaces_the_whole_profile_and_is_audited_without_values(client, db_session, world):
    await login(client, world["counselor"].email)
    assert (await client.put(url(world["student"].id), json=full_body(world["uk"].id))).status_code == 200
    response = await client.put(url(world["student"].id), json={"city": "Pune", "qualifications": [{"level": "master"}]})
    assert response.status_code == 200, response.text
    profile = response.json()["profile"]
    assert profile["city"] == "Pune" and profile["nationality"] is None and profile["english_tests"] == []  # P5: omitted = cleared
    assert [q["level"] for q in profile["qualifications"]] == ["master"]
    sid = world["student"].id
    assert await db_session.scalar(select(func.count()).select_from(OverseasStudentQualification).where(OverseasStudentQualification.student_user_id == sid)) == 1
    assert await db_session.scalar(select(func.count()).select_from(OverseasStudentEnglishTest).where(OverseasStudentEnglishTest.student_user_id == sid)) == 0
    audits = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "overseas_student_profile.update", AuditLog.entity_id == str(sid)).order_by(AuditLog.created_at))).all()
    assert len(audits) == 2 and audits[0].user_id == world["counselor"].id
    assert "passport_number" in audits[0].metadata_json["fields"] and "Z1234567" not in str(audits[0].metadata_json)


@pytest.mark.asyncio
async def test_the_student_edits_every_field_of_their_own_profile(client, db_session, world):
    """P1: all fields; last write wins over the counselor's save."""
    await login(client, world["counselor"].email)
    await client.put(url(world["student"].id), json=full_body(world["uk"].id))
    await login(client, world["student"].email)
    body = full_body(world["uk"].id) | {"city": "Leeds", "english_tests": [{"test_type": "PTE", "status": "booked", "test_date": str(date.today())}]}
    response = await client.put(ME, json=body)
    assert response.status_code == 200, response.text
    assert response.json()["profile"]["city"] == "Leeds" and response.json()["profile"]["updated_by_name"] == world["student"].full_name
    await login(client, world["counselor"].email)
    tests = (await client.get(url(world["student"].id))).json()["profile"]["english_tests"]
    assert [(t["test_type"], t["status"]) for t in tests] == [("PTE", "booked")]


@pytest.mark.asyncio
async def test_the_overseas_admin_reads_and_writes_any_overseas_student(client, db_session, world):
    unlinked = await mk_user(db_session, role="overseas_student")
    await login(client, world["admin"].email)
    response = await client.put(url(unlinked.id), json={"preferred_intake": "Jan 2028"})
    assert response.status_code == 200 and response.json()["profile"]["preferred_intake"] == "Jan 2028"


@pytest.mark.asyncio
async def test_a_linked_walk_in_student_is_in_scope(client, db_session, world):
    from app.models import OverseasStudentCounselor

    walk_in = await mk_user(db_session, role="overseas_student")
    db_session.add(OverseasStudentCounselor(student_user_id=walk_in.id, counselor_user_id=world["counselor"].id, assigned_by_user_id=world["counselor"].id))
    await db_session.commit()
    await login(client, world["counselor"].email)
    assert (await client.put(url(walk_in.id), json={"city": "Delhi"})).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["unknown", "staff", "it_student"])
async def test_unknown_and_non_overseas_students_are_404(client, db_session, world, target):
    sid = {"unknown": uuid.uuid4(), "staff": world["other"].id, "it_student": (await mk_user(db_session, role="it_student", division="it")).id}[target]
    await login(client, world["admin"].email)
    assert (await client.get(url(sid))).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("role,division", [("overseas_student", "overseas"), ("agent", "overseas"), ("university_rep", "overseas"), ("counselor", "it"), ("super_admin", "overseas")])
async def test_other_roles_cannot_use_the_counselor_route(client, db_session, world, role, division):
    caller = await mk_user(db_session, role=role, division=division)
    await login(client, caller.email, division)
    assert (await client.get(url(world["student"].id))).status_code == 403
    assert (await client.put(url(world["student"].id), json={})).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["counselor", "overseas_admin", "agent"])
async def test_only_an_overseas_student_has_a_my_profile(client, db_session, world, role):
    await login(client, (await mk_user(db_session, role=role)).email)
    assert (await client.get(ME)).status_code == 403
    assert (await client.put(ME, json={})).status_code == 403


@pytest.mark.asyncio
async def test_the_student_cannot_write_server_owned_fields(client, world):
    await login(client, world["student"].email)
    for extra in ({"student_user_id": str(world["other"].id)}, {"updated_by_user_id": str(world["other"].id)}, {"qualifications": [{"level": "phd", "id": str(uuid.uuid4())}]}):
        assert (await client.put(ME, json=extra)).status_code == 422, extra


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"date_of_birth": str(date.today() + timedelta(days=1))},
        {"date_of_birth": "1899-12-31"},
        {"passport_number": "AB 12"},
        {"work_experience_months": 601},
        {"preferred_level": "Masters"},
        {"study_mode": "evening"},
        {"budget_min": "10", "budget_max": "5", "budget_currency": "INR"},
        {"budget_min": "10"},
        {"preferred_country_ids": [str(uuid.uuid4())]},
        {"qualifications": [{"level": "bachelor", "score": "8"}]},
        {"qualifications": [{"level": "bachelor", "score_type": "percentage", "score": "101"}]},
        {"qualifications": [{"level": "bachelor", "score_type": "cgpa", "score": "10.5"}]},
        {"qualifications": [{"level": "bachelor", "year_completed": 1949}]},
        {"qualifications": [{"level": "bachelor", "backlogs": -1}]},
        {"qualifications": [{"level": "degree"}]},
        {"qualifications": [{"level": "other"}] * 11},
        {"english_tests": [{"test_type": "IELTS", "overall_score": "9.5"}]},
        {"english_tests": [{"test_type": "PTE", "overall_score": "5"}]},
        {"english_tests": [{"test_type": "TOEFL", "overall_score": "121"}]},
        {"english_tests": [{"test_type": "IELTS", "test_date": "2026-01-10", "valid_until": "2026-01-09"}]},
        {"english_tests": [{"test_type": "IELTS", "test_date": str(date.today() + timedelta(days=1)), "status": "taken"}]},
        {"english_tests": [{"test_type": "GRE"}]},
        {"english_tests": [{"test_type": "Other"}] * 6},
    ],
)
async def test_invalid_values_are_422_and_nothing_is_saved(client, db_session, world, body):
    await login(client, world["counselor"].email)
    response = await client.put(url(world["student"].id), json=body)
    assert response.status_code == 422, (body, response.text)
    assert await db_session.get(OverseasStudentProfile, world["student"].id) is None


@pytest.mark.asyncio
async def test_preferred_countries_must_be_distinct_and_at_most_five(client, db_session, world):
    await login(client, world["counselor"].email)
    uk = str(world["uk"].id)
    assert (await client.put(url(world["student"].id), json={"preferred_country_ids": [uk, uk]})).status_code == 422
    six = [str((await mk_country(db_session, uniq("Land"))).id) for _ in range(6)]
    assert (await client.put(url(world["student"].id), json={"preferred_country_ids": six})).status_code == 422


@pytest.mark.asyncio
async def test_an_english_test_past_its_validity_reads_as_expired(client, world):
    await login(client, world["counselor"].email)
    body = {"english_tests": [{"test_type": "IELTS", "status": "taken", "overall_score": "6.5", "test_date": "2022-01-10", "valid_until": "2024-01-10"}]}
    tests = (await client.put(url(world["student"].id), json=body)).json()["profile"]["english_tests"]
    assert tests[0]["expired"] is True


@pytest.mark.asyncio
async def test_the_agency_reads_the_profile_without_the_passport(client, db_session, world):
    """P2/P3: read-only for the agency of a student with a login; a record with no login has no profile."""
    org = await mk_active_org(db_session, name=uniq("Agency"))
    agent = org["master"]
    linked = AgentStudent(agent_id=agent.id, student_id=world["student"].id, status="active")
    no_login = AgentStudent(agent_id=agent.id, full_name="No Login", status="active")
    db_session.add_all([linked, no_login])
    await db_session.commit()
    await login(client, world["counselor"].email)
    await client.put(url(world["student"].id), json=full_body(world["uk"].id))

    await login(client, agent.email)
    response = await client.get(AGENT.format(linked.id))
    assert response.status_code == 200, response.text
    profile = response.json()["profile"]
    assert [q["level"] for q in profile["qualifications"]] == ["class_12", "bachelor"]
    assert "passport_number" not in profile and "passport_expiry" not in profile
    assert (await client.get(AGENT.format(no_login.id))).json() == {"profile": None}

    stranger = (await mk_active_org(db_session, name=uniq("Other agency")))["master"]
    await login(client, stranger.email)
    assert (await client.get(AGENT.format(linked.id))).status_code == 404


@pytest.mark.asyncio
async def test_the_student_portal_profile_section_reads_the_structured_profile(client, world):
    await login(client, world["counselor"].email)
    await client.put(url(world["student"].id), json=full_body(world["uk"].id))
    await login(client, world["student"].email)
    rows = {r["field"]: r["value"] for r in (await client.get("/api/v1/portal/overseas/student/profile")).json()["rows"]}
    assert rows["Highest qualification"] == "Bachelor's degree — B.Tech CSE"
    assert rows["Preferred countries"] == world["uk"].name and rows["Preferred intake"] == "September 2027"
    assert rows["English test"] == "IELTS 7.5 (taken)"


@pytest.mark.asyncio
async def test_the_students_and_users_tables_link_to_the_profile_page(client, world):
    await login(client, world["counselor"].email)
    rows = (await client.get("/api/v1/portal/overseas/counselor/students")).json()["rows"]
    assert {r["profile"] for r in rows if r["student_id"] == str(world["student"].id)} == {f"/overseas/counselor/students/{world['student'].id}/profile"}
    await login(client, world["admin"].email)
    users = (await client.get("/api/v1/portal/overseas/admin/users")).json()
    assert {"key": "profile", "label": "", "type": "student_profile"} in users["columns"]
    assert {r["profile"] for r in users["rows"] if r["id"] == str(world["student"].id)} == {f"/overseas/admin/students/{world['student'].id}/profile"}
