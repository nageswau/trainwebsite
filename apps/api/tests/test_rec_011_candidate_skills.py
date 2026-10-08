"""rec-011 -- a candidate's skills (spec §1-§4, §7 AC1-AC5; DEC-SCOPE-135 SK1-SK6): one row per skill, the duplicate 409, the Skills Master
422, the status change with who and when, roles, the pool and archived rules. The shared test database is never truncated, so every
assertion uses rows created by the test."""

import asyncio
import random
import uuid
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.main import app
from app.models import AuditLog, Candidate, CandidateSkill, RecCandidateSource, Skill
from tests.rec001_helpers import as_role, login, make_pm, make_recruiter, make_user

CANDIDATES = "/api/v1/recruiter/candidates"
JAVA = {"skill": "Java", "level": "advanced", "experience_months": 36, "last_used_year": 2026, "source": "resume"}


def skills_url(candidate_id, suffix="") -> str:
    return f"{CANDIDATES}/{candidate_id}/skills{suffix}"


async def _candidate(client, db) -> dict:
    source = str(await db.scalar(select(RecCandidateSource.id).where(RecCandidateSource.name == "Referral")))
    body = {"name": "Rahul Sharma", "mobile": "9" + "".join(random.choices("0123456789", k=9)), "email": f"s{uuid.uuid4().hex[:10]}@example.com", "source_id": source}
    response = await client.post(CANDIDATES, json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def _recruiter_with_candidate(client, db):
    recruiter = await make_recruiter(db)
    await login(client, recruiter)
    return recruiter, await _candidate(client, db)


async def _add(client, candidate, **body):
    return await client.post(skills_url(candidate["id"]), json=JAVA | body)


# --- AC1: each skill is its own row ----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_adding_java_stores_one_claimed_row_and_audits_it(client, db_session):
    recruiter, candidate = await _recruiter_with_candidate(client, db_session)
    response = await _add(client, candidate)
    assert response.status_code == 201, response.text
    item = response.json()
    assert item["skill"]["name"] == "Java" and item["skill"]["active"] is True and item["category"]["name"] == "Programming"
    assert (item["level"], item["experience_months"], item["last_used_year"], item["source"]) == ("advanced", 36, 2026, "resume")
    assert item["status"] == "claimed" and item["verified_by"] is None and item["verified_at"] is None
    assert item["added_by"]["id"] == str(recruiter.id)
    second = await _add(client, candidate, skill="Python", level="beginner", experience_months=None, last_used_year=None, source="certification")
    assert second.status_code == 201, second.text
    listing = (await client.get(skills_url(candidate["id"]))).json()
    assert [i["skill"]["name"] for i in listing["items"]] == ["Java", "Python"] and listing["can_edit"] is True
    rows = (await db_session.scalars(select(CandidateSkill).where(CandidateSkill.candidate_id == uuid.UUID(candidate["id"])))).all()
    assert len(rows) == 2
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "candidate.skill_add", AuditLog.entity_id == candidate["id"]).limit(1))
    assert audit is not None and audit.metadata_json["skill_id"] == item["skill"]["id"]


@pytest.mark.asyncio
async def test_source_defaults_to_resume_and_an_alias_resolves_to_its_skill(client, db_session):
    _, candidate = await _recruiter_with_candidate(client, db_session)
    response = await client.post(skills_url(candidate["id"]), json={"skill": "  j2ee ", "level": "expert"})
    assert response.status_code == 201, response.text
    assert response.json()["skill"]["name"] == "Java" and response.json()["source"] == "resume"


# --- AC2: duplicates -------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("again", ["Java", "JAVA", "J2EE"])
async def test_the_same_skill_again_is_409(client, db_session, again):
    _, candidate = await _recruiter_with_candidate(client, db_session)
    assert (await _add(client, candidate)).status_code == 201
    response = await _add(client, candidate, skill=again)
    assert response.status_code == 409
    assert response.json()["detail"] == "Java is already on this candidate's skills"


@pytest.mark.asyncio
async def test_two_concurrent_adds_of_one_skill_give_one_201_and_one_409(db_session):
    recruiter = await make_recruiter(db_session)
    clients = [AsyncClient(transport=ASGITransport(app=app), base_url="http://test") for _ in range(2)]
    try:
        for c in clients:
            await login(c, recruiter)
        candidate = await _candidate(clients[0], db_session)
        results = await asyncio.gather(*(_add(c, candidate) for c in clients))
    finally:
        for c in clients:
            await c.aclose()
    assert sorted(r.status_code for r in results) == [201, 409]


# --- AC4: the Skills Master decides --------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_skill_not_in_the_master_is_422_naming_it(client, db_session):
    _, candidate = await _recruiter_with_candidate(client, db_session)
    response = await _add(client, candidate, skill="Kobol 2049")
    assert response.status_code == 422
    assert response.json()["detail"] == "“Kobol 2049” is not in the Skills Master. Pick a listed skill, or ask your manager to add it or an alias."


@pytest.mark.asyncio
async def test_an_inactive_skill_is_not_addable(client, db_session):
    _, candidate = await _recruiter_with_candidate(client, db_session)
    category_id = await db_session.scalar(select(Skill.category_id).where(Skill.name == "Java"))
    skill = Skill(name=f"Retired {uuid.uuid4().hex[:6]}", category_id=category_id, active=False)
    db_session.add(skill)
    await db_session.commit()
    assert (await _add(client, candidate, skill=skill.name)).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"level": "guru"}, "Level: "),
        ({"level": None}, "Level is required"),
        ({"skill": ""}, "Skill: "),
        ({"experience_months": 601}, "Experience (months) must be between 0 and 600"),
        ({"last_used_year": 1949}, "Last used must be a year between 1950 and "),
        ({"last_used_year": datetime.now(UTC).year + 1}, "Last used must be a year between 1950 and "),
        ({"source": "linkedin"}, "Source: "),
        ({"status": "verified"}, "Unknown field: status"),
    ],
)
async def test_invalid_bodies_are_one_readable_422(client, db_session, change, message):
    _, candidate = await _recruiter_with_candidate(client, db_session)
    response = await _add(client, candidate, **change)
    assert response.status_code == 422
    assert response.json()["detail"].startswith(message), response.json()


@pytest.mark.asyncio
async def test_at_most_100_skills_per_candidate(client, db_session, monkeypatch):
    from app.services import candidate_skills

    monkeypatch.setattr(candidate_skills, "MAX_SKILLS", 1)
    _, candidate = await _recruiter_with_candidate(client, db_session)
    assert (await _add(client, candidate)).status_code == 201
    response = await _add(client, candidate, skill="Python")
    assert response.status_code == 422 and response.json()["detail"] == "A candidate can have at most 1 skills"


# --- edit and remove -------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_patch_changes_only_what_is_sent_and_a_no_op_writes_no_audit(client, db_session):
    _, candidate = await _recruiter_with_candidate(client, db_session)
    item = (await _add(client, candidate)).json()
    url = skills_url(candidate["id"], f"/{item['id']}")
    response = await client.patch(url, json={"level": "expert", "last_used_year": None})
    assert response.status_code == 200, response.text
    assert (response.json()["level"], response.json()["last_used_year"], response.json()["experience_months"]) == ("expert", None, 36)
    audits = select(func.count()).select_from(AuditLog).where(AuditLog.action == "candidate.skill_update", AuditLog.entity_id == candidate["id"])
    assert await db_session.scalar(audits) == 1
    assert (await client.patch(url, json={"level": "expert"})).status_code == 200
    assert await db_session.scalar(audits) == 1
    assert (await client.patch(url, json={"skill": "Python"})).json()["detail"] == "Unknown field: skill"
    assert (await client.patch(url, json={"source": None})).json()["detail"] == "Source is required"


@pytest.mark.asyncio
async def test_remove_deletes_the_row_and_audits_it(client, db_session):
    _, candidate = await _recruiter_with_candidate(client, db_session)
    item = (await _add(client, candidate)).json()
    url = skills_url(candidate["id"], f"/{item['id']}")
    assert (await client.delete(url)).status_code == 204
    assert (await client.get(skills_url(candidate["id"]))).json()["items"] == []
    assert (await client.delete(url)).status_code == 404
    assert await db_session.scalar(select(AuditLog.id).where(AuditLog.action == "candidate.skill_remove", AuditLog.entity_id == candidate["id"]))
    assert (await _add(client, candidate)).status_code == 201  # it can be added again


@pytest.mark.asyncio
async def test_a_skill_id_of_another_candidate_is_404(client, db_session):
    _, first = await _recruiter_with_candidate(client, db_session)
    second = await _candidate(client, db_session)
    item = (await _add(client, first)).json()
    for call in (
        client.patch(skills_url(second["id"], f"/{item['id']}"), json={"level": "expert"}),
        client.delete(skills_url(second["id"], f"/{item['id']}")),
        client.post(skills_url(second["id"], f"/{item['id']}/status"), json={"status": "verified"}),
    ):
        response = await call
        assert response.status_code == 404 and response.json()["detail"] == "Skill not found on this candidate"


# --- AC3: status changes record who and when ------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_status_change_records_who_and_when_and_claimed_clears_them(client, db_session):
    recruiter, candidate = await _recruiter_with_candidate(client, db_session)
    item = (await _add(client, candidate)).json()
    url = skills_url(candidate["id"], f"/{item['id']}/status")
    verified = await client.post(url, json={"status": "verified"})
    assert verified.status_code == 200, verified.text
    assert verified.json()["status"] == "verified" and verified.json()["verified_by"] == {"id": str(recruiter.id), "full_name": recruiter.full_name}
    assert verified.json()["verified_at"] is not None
    assert (await client.post(url, json={"status": "verified"})).status_code == 409
    manager = await make_pm(db_session)
    await login(client, manager)
    assessed = (await client.post(url, json={"status": "assessed"})).json()
    assert assessed["status"] == "assessed" and assessed["verified_by"]["id"] == str(manager.id)
    claimed = (await client.post(url, json={"status": "claimed"})).json()
    assert claimed["status"] == "claimed" and claimed["verified_by"] is None and claimed["verified_at"] is None
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "candidate.skill_status", AuditLog.entity_id == candidate["id"]).order_by(AuditLog.created_at))).all()
    assert [(r.metadata_json["from"], r.metadata_json["to"], r.user_id) for r in rows] == [
        ("claimed", "verified", recruiter.id),
        ("verified", "assessed", manager.id),
        ("assessed", "claimed", manager.id),
    ]
    assert (await client.post(url, json={"status": "certified"})).status_code == 422


# --- AC5: roles, pool and archived -----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("employer", "it"), ("it_admin", "it"), ("it_student", "it"), ("bdm", "it")])
async def test_outsiders_are_refused_before_anything_is_read(client, db_session, role, division):
    await as_role(client, db_session, role, division)
    unknown = uuid.uuid4()
    assert (await client.get(skills_url(unknown))).status_code == 403
    assert (await client.post(skills_url(unknown), json=JAVA)).status_code == 403
    assert (await client.post(skills_url(unknown, f"/{uuid.uuid4()}/status"), json={"status": "verified"})).status_code == 403


@pytest.mark.asyncio
async def test_hr_team_reads_but_never_writes(client, db_session):
    _, candidate = await _recruiter_with_candidate(client, db_session)
    item = (await _add(client, candidate)).json()
    await login(client, await make_user(db_session, role="hr_team", division="it"))
    listing = await client.get(skills_url(candidate["id"]))
    assert listing.status_code == 200 and listing.json()["can_edit"] is False and len(listing.json()["items"]) == 1
    assert (await _add(client, candidate, skill="Python")).status_code == 403
    assert (await client.patch(skills_url(candidate["id"], f"/{item['id']}"), json={"level": "expert"})).status_code == 403
    assert (await client.delete(skills_url(candidate["id"], f"/{item['id']}"))).status_code == 403
    assert (await client.post(skills_url(candidate["id"], f"/{item['id']}/status"), json={"status": "verified"})).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["placement_manager", "super_admin"])
async def test_managers_and_super_admin_write(client, db_session, role):
    _, candidate = await _recruiter_with_candidate(client, db_session)
    await as_role(client, db_session, role, "it")
    assert (await _add(client, candidate)).status_code == 201


@pytest.mark.asyncio
async def test_an_archived_candidate_is_read_only(client, db_session):
    _, candidate = await _recruiter_with_candidate(client, db_session)
    item = (await _add(client, candidate)).json()
    assert (await client.post(f"{CANDIDATES}/{candidate['id']}/archive")).status_code == 200
    assert (await client.get(skills_url(candidate["id"]))).json()["can_edit"] is False
    for call in (
        _add(client, candidate, skill="Python"),
        client.patch(skills_url(candidate["id"], f"/{item['id']}"), json={"level": "expert"}),
        client.delete(skills_url(candidate["id"], f"/{item['id']}")),
        client.post(skills_url(candidate["id"], f"/{item['id']}/status"), json={"status": "verified"}),
    ):
        response = await call
        assert response.status_code == 409 and response.json()["detail"] == "Restore this candidate first"


@pytest.mark.asyncio
async def test_a_candidate_outside_the_pool_or_unknown_is_404(client, db_session):
    _, candidate = await _recruiter_with_candidate(client, db_session)
    row = await db_session.get(Candidate, uuid.UUID(candidate["id"]))
    row.user_id = (await make_user(db_session, role="it_student", division="it")).id
    await db_session.commit()
    assert (await client.get(skills_url(candidate["id"]))).status_code == 404
    assert (await _add(client, candidate)).status_code == 404
    assert (await client.get(skills_url(uuid.uuid4()))).status_code == 404


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    assert (await client.get(skills_url(uuid.uuid4()))).status_code == 401
