"""hrc-010 (DEC-SCOPE-381, spec docs/superpowers/specs/2026-11-04-hrc-010-candidate-profile-design.md): the §5 profile -- education,
employment and certification rows (P1-P3, P7), derived total experience (P4, Q-09), the legacy fields as mirrors (P5), the richer skills,
preferences and contact (P7-P9) and the Appendix B completeness (P10)."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog, Candidate, CandidateEducation, Skill, SkillCategory
from app.services import candidate_profile as profile
from tests.rec038_helpers import add, core, headers, make_candidate, tag

pytestmark = pytest.mark.asyncio
CANDIDATES = "/api/v1/recruiter/candidates"
DEGREE = {"degree": "B.Tech", "specialisation": "Computer Science", "institution": "JNTU Hyderabad", "year": 2018, "grade": "8.2 CGPA"}


def _u(world, role="rec"):
    return headers(world["users"][role])


def _path(world, suffix=""):
    return f"{CANDIDATES}/{world['candidate']}{suffix}"


def _job(employer, start, end=None, **extra):
    return {"employer": employer, "designation": "Developer", "industry": "IT services", "employment_type": "full_time", "start_date": start,
            "end_date": end, **extra}  # fmt: skip


# --- P4: total experience ---------------------------------------------------------------------------------------------------------------
async def test_total_experience_counts_an_overlap_once():
    today = date(2026, 1, 1)
    assert profile.experience_months([], today) is None
    # AC2 / E: Jan 2020-Dec 2020 and Jul 2020-Jun 2021 overlap for six months -> 18 months, not 24
    assert profile.experience_months([(date(2020, 1, 1), date(2020, 12, 31)), (date(2020, 7, 1), date(2021, 6, 30))], today) == 18
    # touching periods join; a period inside another adds nothing
    assert profile.experience_months([(date(2020, 1, 1), date(2020, 6, 30)), (date(2020, 7, 1), date(2020, 12, 31)), (date(2020, 3, 1), date(2020, 4, 1))], today) == 12
    # E: a current job (no end date) runs to today
    assert profile.experience_months([(date(2025, 1, 1), None)], today) == 12


# --- AC4 / AC1 through the API ----------------------------------------------------------------------------------------------------------
async def test_two_jobs_and_a_degree_derive_experience_and_the_legacy_fields(client, db_session):
    world = await core(client, db_session)
    body = {"education": [DEGREE], "employment": [_job("Infosys", "2019-01-01", "2019-12-31"), _job("TCS", "2020-01-01", "2021-12-31")],
            "experience_months": 5}  # fmt: skip  # P4: ignored while there are employment rows
    response = await client.patch(_path(world), json=body, headers=_u(world))
    assert response.status_code == 200, response.text
    out = response.json()
    assert out["education"] == [DEGREE]
    assert [j["employer"] for j in out["employment"]] == ["Infosys", "TCS"] and out["employment"][1]["end_date"] == "2021-12-31"
    assert out["experience_months"] == 36 and out["is_fresher"] is False  # 3 years, derived
    assert (out["qualification"], out["college"], out["passing_year"]) == ("B.Tech", "JNTU Hyderabad", 2018)  # P5 mirrors
    assert out["current_company"] is None  # no current job
    out = (await client.patch(_path(world), json={"employment": [_job("Wipro", (date.today() - timedelta(days=365)).isoformat())]}, headers=_u(world))).json()
    assert out["current_company"] == "Wipro" and out["experience_months"] == 12


async def test_every_section_5_field_can_be_saved(client, db_session):
    world = await core(client, db_session)
    body = {
        "country": "India", "state": "Telangana", "city": "Hyderabad", "preferred_contact": "whatsapp", "relevant_experience_months": 18,
        "tools": ["Git", "Jira"], "languages": ["English", "Telugu"], "preferred_roles": ["Java Developer", "Backend Engineer"],
        "work_modes": ["remote", "hybrid"],  # kept in the enum's order "employment_types": ["full_time"], "shifts": ["day"], "available_from": "2026-12-01",
        "willing_to_relocate": True, "certifications": [{"name": "AWS Developer", "issuer": "Amazon", "issued_on": "2024-03-01", "expires_on": "2027-03-01",
                                                          "credential_id": "AWS-123"}],
    }  # fmt: skip
    response = await client.patch(_path(world), json=body, headers=_u(world))
    assert response.status_code == 200, response.text
    out = (await client.get(_path(world), headers=_u(world))).json()
    for key, value in body.items():
        assert out[key] == value, key
    assert out["location"] == "Hyderabad, Telangana, India" and out["preferred_role"] == "Java Developer"  # P5 mirrors
    assert out["email_verified_at"] is None


async def test_create_takes_the_rows(client, db_session):
    world = await core(client, db_session)
    source = (await client.get("/api/v1/recruiter/catalogue/candidate-sources", headers=_u(world))).json()
    source_id = next(s["id"] for s in source["items"] if s["active"])
    body = {"name": f"Priya {tag()}", "email": f"{tag('p10-')}@example.com", "source_id": source_id, "education": [DEGREE],
            "employment": [_job("Infosys", "2019-01-01", "2019-12-31")]}  # fmt: skip
    response = await client.post(CANDIDATES, json=body, headers=_u(world))
    assert response.status_code == 201, response.text
    out = response.json()
    assert out["education"] == [DEGREE] and out["experience_months"] == 12 and out["qualification"] == "B.Tech"


# --- AC5 / validation ------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"employment": [_job("A", "2020-01-01", "2020-12-31"), _job("B", "2021-05-01", "2021-04-01")]}, "Employment 2: the end date must be on or after the start date"),
        ({"employment": [_job("A", "2999-01-01")]}, "Employment 1: the start date cannot be in the future"),
        ({"employment": [{"designation": "Dev", "start_date": "2020-01-01"}]}, "Employment 1: enter the employer"),
        ({"education": [{"degree": " "}]}, "Education 1: enter the degree or the institution"),
        ({"certifications": [{"name": "X", "issued_on": "2024-01-01", "expires_on": "2023-01-01"}]}, "Certification 1: the expiry date must be on or after the issue date"),
        ({"work_modes": ["space"]}, "Work modes"),
        ({"preferred_contact": "pigeon"}, "Preferred contact"),
        ({"education": [DEGREE] * 11}, "Enter at most 10 education rows"),
        ({"email_verified_at": "2026-01-01T00:00:00Z"}, None),  # P9: not an input
    ],
)  # fmt: skip
async def test_invalid_profile_values_are_422(client, db_session, body, message):
    world = await core(client, db_session)
    response = await client.patch(_path(world), json=body, headers=_u(world))
    assert response.status_code == 422, response.text
    if message:
        assert message in str(response.json()["detail"]), response.text


async def test_hr_team_reads_but_cannot_write_the_profile(client, db_session):
    world = await core(client, db_session)
    assert (await client.patch(_path(world), json={"education": [DEGREE]}, headers=_u(world, "hr"))).status_code == 403
    assert "education" in (await client.get(_path(world), headers=_u(world, "hr"))).json()


# --- P4/P5 compatibility ----------------------------------------------------------------------------------------------------------------
async def test_legacy_clients_keep_working_without_rows(client, db_session):
    world = await core(client, db_session)
    body = {"experience_months": 0, "qualification": "MCA", "current_company": "Acme", "preferred_role": "Tester", "location": "Pune"}
    out = (await client.patch(_path(world), json=body, headers=_u(world))).json()
    assert (out["experience_months"], out["is_fresher"], out["qualification"], out["current_company"]) == (0, True, "MCA", "Acme")
    assert out["preferred_roles"] == ["Tester"] and out["location"] == "Pune" and out["education"] == []


# --- P9 ---------------------------------------------------------------------------------------------------------------------------------
async def test_changing_the_email_clears_its_verification(client, db_session):
    world = await core(client, db_session)
    candidate = await db_session.get(Candidate, world["candidate"])
    candidate.email_verified_at = datetime.now(UTC)
    await db_session.commit()
    assert (await client.get(_path(world), headers=_u(world))).json()["email_verified_at"] is not None
    out = (await client.patch(_path(world), json={"email": f"{tag('n10-')}@example.com"}, headers=_u(world))).json()
    assert out["email_verified_at"] is None


# --- P10: completeness ------------------------------------------------------------------------------------------------------------------
async def test_completeness_follows_appendix_b(client, db_session):
    world = await core(client, db_session)
    out = (await client.get(_path(world), headers=_u(world))).json()
    assert out["completeness"]["percent"] == 0
    assert [(i["key"], i["weight"]) for i in out["completeness"]["items"]] == [
        ("contact_verified", 10), ("education", 15), ("skills", 15), ("experience", 15), ("preferences", 15), ("resume", 20), ("compensation", 10),
    ]  # fmt: skip
    body = {"education": [DEGREE], "experience_months": 0, "preferred_roles": ["Java Developer"], "preferred_locations": ["Pune"], "expected_salary": "600000"}
    out = (await client.patch(_path(world), json=body, headers=_u(world))).json()
    assert out["completeness"]["percent"] == 15 + 15 + 15 + 10
    category = await add(db_session, SkillCategory(name=f"H10 {tag()}"))
    for _ in range(3):
        skill = await add(db_session, Skill(name=f"H10 skill {tag()}", category_id=category.id))
        await db_session.commit()
        assert (await client.post(_path(world, "/skills"), json={"skill": skill.name, "level": "beginner"}, headers=_u(world))).status_code == 201
    candidate = await db_session.get(Candidate, world["candidate"])
    candidate.email_verified_at = datetime.now(UTC)
    await db_session.commit()
    out = (await client.get(_path(world), headers=_u(world))).json()
    assert out["completeness"]["percent"] == 80 and {i["key"] for i in out["completeness"]["items"] if not i["met"]} == {"resume"}


# --- hrc-003 / hrc-004 ------------------------------------------------------------------------------------------------------------------
async def test_a_rows_only_save_bumps_the_version_and_is_audited(client, db_session):
    world = await core(client, db_session)
    first = (await client.get(_path(world), headers=_u(world))).json()
    response = await client.patch(_path(world), json={"education": [DEGREE], "expected_updated_at": first["updated_at"]}, headers=_u(world))
    assert response.status_code == 200, response.text
    assert response.json()["updated_at"] != first["updated_at"]
    stale = await client.patch(_path(world), json={"education": [], "expected_updated_at": first["updated_at"]}, headers=_u(world))
    assert stale.status_code == 409  # the old version is now stale
    row = await db_session.scalar(select(AuditLog).where(AuditLog.action == "candidate.update", AuditLog.entity_id == world["candidate"]).order_by(AuditLog.created_at.desc()))
    assert "education" in row.metadata_json["fields"]
    assert row.metadata_json["changes"]["education"] == [None, "B.Tech · Computer Science · JNTU Hyderabad · 2018 · 8.2 CGPA"]


# --- P7: primary skills -----------------------------------------------------------------------------------------------------------------
async def test_a_skill_can_be_primary(client, db_session):
    world = await core(client, db_session)
    category = await add(db_session, SkillCategory(name=f"H10p {tag()}"))
    skill = await add(db_session, Skill(name=f"H10 primary {tag()}", category_id=category.id))
    await db_session.commit()
    created = await client.post(_path(world, "/skills"), json={"skill": skill.name, "level": "expert", "is_primary": True}, headers=_u(world))
    assert created.status_code == 201, created.text and created.json()["is_primary"] is True
    item = created.json()["id"]
    assert (await client.patch(_path(world, f"/skills/{item}"), json={"is_primary": False}, headers=_u(world))).json()["is_primary"] is False
    assert (await client.patch(_path(world, f"/skills/{item}"), json={"is_primary": None}, headers=_u(world))).status_code == 422


# --- P12: merge ------------------------------------------------------------------------------------------------------------------------
async def test_a_merge_moves_the_rows_when_the_survivor_has_none(client, db_session):
    world = await core(client, db_session)
    victim = await make_candidate(db_session, world["users"]["rec"])
    await db_session.commit()
    patched = await client.patch(f"{CANDIDATES}/{victim.id}", json={"education": [DEGREE], "employment": [_job("Infosys", "2019-01-01", "2019-12-31")]}, headers=_u(world))
    assert patched.status_code == 200, patched.text
    response = await client.post(_path(world, "/merge"), json={"victim_code": victim.candidate_code}, headers=_u(world, "mgr"))
    assert response.status_code == 200, response.text
    out = (await client.get(_path(world), headers=_u(world))).json()
    assert out["education"] == [DEGREE] and out["experience_months"] == 12 and out["qualification"] == "B.Tech"
    assert await db_session.scalar(select(CandidateEducation.id).where(CandidateEducation.candidate_id == victim.id)) is None
