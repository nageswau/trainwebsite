"""rec-012 -- extract a resume's suggestions and apply the chosen ones (spec §1, §4, §6 AC1-AC8; DEC-SCOPE-148 EX1-EX10). The shared
test database is never truncated, so every assertion uses rows created by the test."""

import asyncio
import io
import uuid

import pytest
from pypdf import PdfWriter
from sqlalchemy import select

from app.models import AuditLog, Candidate, CandidateResume, CandidateSkill, Skill
from app.services import resume_extraction as svc
from tests.rec001_helpers import as_role
from tests.test_rec_009_candidates import BASE, as_recruiter, create
from tests.test_rec_009_resumes import upload
from tests.test_rec_012_resume_extract import SOURCE, _docx, _pdf

FIVE = ["Java", "Spring Boot", "Hibernate", "REST API", "MySQL"]


def url(candidate_id, version, action="extract") -> str:
    return f"{BASE}/{candidate_id}/resume/{version}/{action}"


async def _with_resume(client, db, data: bytes = None):
    await as_recruiter(client, db)
    candidate = await create(client, db)
    response = await upload(client, candidate["id"], data or _pdf(SOURCE))
    assert response.status_code == 201, response.text
    return candidate, response.json()["version"]


async def _extracted(client, db, data: bytes = None):
    candidate, version = await _with_resume(client, db, data)
    response = await client.post(url(candidate["id"], version))
    assert response.status_code == 200, response.text
    return candidate, version, response.json()


async def _skill_id(db, name: str) -> str:
    return str(await db.scalar(select(Skill.id).where(Skill.name == name)))


# --- extract (AC1-AC3) -----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_extract_suggests_the_source_skills_stores_the_text_and_changes_nothing_else(client, db_session):
    candidate, version, body = await _extracted(client, db_session)
    names = [s["skill"]["name"] for s in body["skills"]]
    assert [n for n in names if n in FIVE] == FIVE and "Spring" not in names  # AC1
    java = body["skills"][0]
    assert java["category"]["name"] == "Programming" and java["matched"] == "Java" and java["on_profile"] is False
    assert (body["version"], body["no_text"], body["truncated"]) == (version, False, False)
    assert body["text_chars"] > 50 and body["extracted_at"]
    for key in ("qualification", "experience_months", "location"):
        assert key in body
    for key in ("job_titles", "certifications", "industries"):
        assert isinstance(body[key], list)
    candidate_id = uuid.UUID(candidate["id"])
    resume = await db_session.scalar(select(CandidateResume).where(CandidateResume.candidate_id == candidate_id))
    await db_session.refresh(resume)
    assert "Hibernate" in resume.extracted_text and resume.extraction_json["skills"][0]["matched"] == "Java"
    # AC2: nothing reaches the candidate until Apply.
    assert await db_session.scalar(select(CandidateSkill.id).where(CandidateSkill.candidate_id == candidate_id)) is None
    row = await db_session.get(Candidate, candidate_id)
    await db_session.refresh(row)
    assert (row.qualification, row.experience_months, row.location) == (None, None, None)
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "candidate.resume_extract", AuditLog.entity_id == candidate["id"]))
    assert audit.metadata_json["version"] == version and audit.metadata_json["skills"] >= 5
    assert "Hibernate" not in str(audit.metadata_json)  # the text never reaches the audit


@pytest.mark.asyncio
async def test_a_skill_already_on_the_profile_is_marked(client, db_session):
    candidate, version = await _with_resume(client, db_session)
    added = await client.post(f"{BASE}/{candidate['id']}/skills", json={"skill": "Java", "level": "advanced"})
    assert added.status_code == 201, added.text
    body = (await client.post(url(candidate["id"], version))).json()
    marks = {s["skill"]["name"]: s["on_profile"] for s in body["skills"]}
    assert marks["Java"] is True and marks["MySQL"] is False


@pytest.mark.asyncio
async def test_a_docx_yields_skills_and_three_years(client, db_session):
    data = _docx("Ravi Kumar", "B.Tech, 3 years of experience.", "Location: Pune", table=[["Skills", "Java, Spring Boot, MySQL"]])
    _, _, body = await _extracted(client, db_session, data)
    assert [s["skill"]["name"] for s in body["skills"] if s["skill"]["name"] in FIVE] == ["Java", "Spring Boot", "MySQL"]
    assert (body["experience_months"], body["qualification"], body["location"]) == (36, "B.Tech", "Pune")


@pytest.mark.asyncio
async def test_a_scanned_pdf_reports_no_text(client, db_session):
    """AC3."""
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.rect(40, 40, 200, 200, fill=1)
    pdf.showPage()
    pdf.save()
    candidate, _, body = await _extracted(client, db_session, buffer.getvalue())
    assert body["no_text"] is True and body["skills"] == [] and body["text_chars"] == 0
    resume = await db_session.scalar(select(CandidateResume).where(CandidateResume.candidate_id == uuid.UUID(candidate["id"])))
    await db_session.refresh(resume)
    assert resume.extracted_text == ""


@pytest.mark.asyncio
async def test_an_encrypted_pdf_is_a_readable_422(client, db_session):
    writer = PdfWriter()
    writer.append(io.BytesIO(_pdf(SOURCE)))
    writer.encrypt(user_password="secret", owner_password="owner")
    buffer = io.BytesIO()
    writer.write(buffer)
    candidate, version = await _with_resume(client, db_session, buffer.getvalue())
    response = await client.post(url(candidate["id"], version))
    assert response.status_code == 422 and "password-protected" in response.json()["detail"]


@pytest.mark.asyncio
async def test_extraction_that_runs_too_long_is_a_readable_422(client, db_session, monkeypatch):
    candidate, version = await _with_resume(client, db_session)
    monkeypatch.setattr(svc, "TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(svc.rx, "read_text", lambda data, content_type: __import__("time").sleep(0.5) or ("", False))
    response = await client.post(url(candidate["id"], version))
    assert response.status_code == 422 and "too long" in response.json()["detail"]


@pytest.mark.asyncio
async def test_extract_unknown_version_candidate_and_archived(client, db_session):
    candidate, version = await _with_resume(client, db_session)
    assert (await client.post(url(candidate["id"], version + 1))).status_code == 404
    assert (await client.post(url(uuid.uuid4(), 1))).status_code == 404
    assert (await client.post(f"{BASE}/{candidate['id']}/archive")).status_code == 200
    response = await client.post(url(candidate["id"], version))
    assert response.status_code == 409 and response.json()["detail"] == "Restore this candidate first"


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["extract", "apply"])
async def test_hr_team_and_outsiders_cannot_extract_or_apply(client, db_session, action):
    candidate, version = await _with_resume(client, db_session)
    for role, division in (("hr_team", "it"), ("it_student", "it"), ("telecaller", "global")):
        await as_role(client, db_session, role, division)
        assert (await client.post(url(candidate["id"], version, action), json={})).status_code == 403


# --- apply (EX6, EX7) ------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_apply_adds_the_chosen_skills_and_fields(client, db_session):
    candidate, version, _ = await _extracted(client, db_session)
    java, mysql = await _skill_id(db_session, "Java"), await _skill_id(db_session, "MySQL")
    body = {"skills": [{"skill_id": java, "level": "advanced"}, {"skill_id": mysql, "level": "intermediate"}], "qualification": "B.Tech", "experience_months": 36, "location": "Pune"}
    response = await client.post(url(candidate["id"], version, "apply"), json=body)
    assert response.status_code == 200, response.text
    assert response.json() == {"skills_added": 2, "fields": ["experience_months", "location", "qualification"]}
    items = (await client.get(f"{BASE}/{candidate['id']}/skills")).json()["items"]
    assert [(i["skill"]["name"], i["level"], i["source"], i["status"]) for i in items] == [("Java", "advanced", "resume", "claimed"), ("MySQL", "intermediate", "resume", "claimed")]
    detail = (await client.get(f"{BASE}/{candidate['id']}")).json()
    assert (detail["qualification"], detail["experience_months"], detail["location"]) == ("B.Tech", 36, "Pune")
    actions = (await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id == candidate["id"]))).all()
    assert actions.count("candidate.skill_add") == 2 and "candidate.resume_apply" in actions
    apply_row = await db_session.scalar(select(AuditLog).where(AuditLog.action == "candidate.resume_apply", AuditLog.entity_id == candidate["id"]))
    assert apply_row.metadata_json == {"version": version, "skill_ids": [java, mysql], "fields": ["experience_months", "location", "qualification"]}


@pytest.mark.asyncio
async def test_apply_only_fields(client, db_session):
    candidate, version, _ = await _extracted(client, db_session)
    response = await client.post(url(candidate["id"], version, "apply"), json={"location": "Hyderabad"})
    assert response.status_code == 200 and response.json() == {"skills_added": 0, "fields": ["location"]}


@pytest.mark.asyncio
async def test_apply_is_all_or_nothing_when_a_skill_is_already_on_the_profile(client, db_session):
    candidate, version, _ = await _extracted(client, db_session)
    assert (await client.post(f"{BASE}/{candidate['id']}/skills", json={"skill": "MySQL", "level": "beginner"})).status_code == 201
    body = {"skills": [{"skill_id": await _skill_id(db_session, "Java"), "level": "advanced"}, {"skill_id": await _skill_id(db_session, "MySQL"), "level": "expert"}], "location": "Pune"}
    response = await client.post(url(candidate["id"], version, "apply"), json=body)
    assert response.status_code == 409 and response.json()["detail"] == "MySQL is already on this candidate's skills"
    items = (await client.get(f"{BASE}/{candidate['id']}/skills")).json()["items"]
    assert [(i["skill"]["name"], i["level"]) for i in items] == [("MySQL", "beginner")]
    assert (await client.get(f"{BASE}/{candidate['id']}")).json()["location"] is None


@pytest.mark.asyncio
async def test_apply_refusals(client, db_session):
    candidate, version, _ = await _extracted(client, db_session)
    java = await _skill_id(db_session, "Java")
    apply_url = url(candidate["id"], version, "apply")
    cases = [
        ({}, 422, "Choose at least one suggestion to save"),
        ({"skills": []}, 422, "Choose at least one suggestion to save"),
        ({"skills": [{"skill_id": java, "level": "advanced"}, {"skill_id": java, "level": "beginner"}]}, 422, "Each skill can be chosen once"),
        ({"skills": [{"skill_id": str(uuid.uuid4()), "level": "advanced"}]}, 422, "is not in the Skills Master"),
        ({"skills": [{"skill_id": java, "level": "guru"}]}, 422, "Each chosen skill: Input should be"),
        ({"skills": [{"level": "advanced"}]}, 422, "Each chosen skill is required"),
        ({"experience_months": 601}, 422, "Total experience (months)"),
        ({"name": "X"}, 422, ""),
    ]
    for body, status, message in cases:
        response = await client.post(apply_url, json=body)
        assert response.status_code == status, (body, response.text)
        assert message in response.json()["detail"], (body, response.text)
    assert (await client.get(f"{BASE}/{candidate['id']}/skills")).json()["items"] == []


@pytest.mark.asyncio
async def test_the_level_defaults_to_intermediate(client, db_session):
    candidate, version, _ = await _extracted(client, db_session)
    response = await client.post(url(candidate["id"], version, "apply"), json={"skills": [{"skill_id": await _skill_id(db_session, "Hibernate")}]})
    assert response.status_code == 200, response.text
    assert [i["level"] for i in (await client.get(f"{BASE}/{candidate['id']}/skills")).json()["items"]] == ["intermediate"]


@pytest.mark.asyncio
async def test_apply_refuses_an_inactive_skill(client, db_session):
    candidate, version, _ = await _extracted(client, db_session)
    category = await db_session.scalar(select(Skill.category_id).where(Skill.name == "Java"))
    inactive = Skill(name=f"Old {uuid.uuid4().hex[:8]}", category_id=category, active=False)
    db_session.add(inactive)
    await db_session.commit()
    response = await client.post(url(candidate["id"], version, "apply"), json={"skills": [{"skill_id": str(inactive.id), "level": "advanced"}]})
    assert response.status_code == 422 and "is not in the Skills Master" in response.json()["detail"]


@pytest.mark.asyncio
async def test_apply_needs_an_extraction_first(client, db_session):
    candidate, version = await _with_resume(client, db_session)
    response = await client.post(url(candidate["id"], version, "apply"), json={"location": "Pune"})
    assert response.status_code == 409 and response.json()["detail"] == "Extract this resume before saving its details"


@pytest.mark.asyncio
async def test_apply_respects_the_skill_cap(client, db_session, monkeypatch):
    from app.services import candidate_skills

    candidate, version, _ = await _extracted(client, db_session)
    monkeypatch.setattr(candidate_skills, "MAX_SKILLS", 1)
    body = {"skills": [{"skill_id": await _skill_id(db_session, n), "level": "advanced"} for n in ("Java", "MySQL")]}
    response = await client.post(url(candidate["id"], version, "apply"), json=body)
    assert response.status_code == 422 and "at most 1 skills" in response.json()["detail"]
    assert (await client.get(f"{BASE}/{candidate['id']}/skills")).json()["items"] == []


@pytest.mark.asyncio
async def test_two_concurrent_extracts_of_one_resume_both_succeed(client, db_session):
    candidate, version = await _with_resume(client, db_session)
    first, second = await asyncio.gather(client.post(url(candidate["id"], version)), client.post(url(candidate["id"], version)))
    assert (first.status_code, second.status_code) == (200, 200)
