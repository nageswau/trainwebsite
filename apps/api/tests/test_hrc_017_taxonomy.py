"""hrc-017 (DEC-SCOPE-388 T1-T9): category domains, the domain filter, a job skill's minimum level and the matching rule it drives (AC2).
The shared test database is never truncated: every test makes its own names (rec-016's World)."""

import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog, CandidateSkill, SkillCategory
from tests.rec001_helpers import as_role
from tests.test_rec_016_matching import REQ, _body, _job_skills, _matches, _weights, _world

CATS, SKILLS = "/api/v1/recruiter/skill-categories", "/api/v1/recruiter/skills"


async def _level(db, candidate, skill, level):
    row = await db.scalar(select(CandidateSkill).where(CandidateSkill.candidate_id == candidate.id, CandidateSkill.skill_id == skill.id))
    row.level = level
    await db.commit()


# --- domains (T1, T4) ---------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_seeded_pharmacy_is_non_it_and_the_it_seed_stays_it(client, db_session):
    """AC1 through the API: the seed's Pharmacy category is listed under non-IT with its skills; Programming is IT."""
    await as_role(client, db_session, "placement_team", "it")
    non_it = _body(await client.get(CATS, params={"domain": "non_it", "limit": 100}))
    names = {c["name"]: c for c in non_it["items"]}
    assert names["Pharmacy"]["domain"] == "non_it" and "Programming" not in names
    assert {"Engineering", "Healthcare", "Finance", "Sales", "Human Resources"} <= set(names)
    it = _body(await client.get(CATS, params={"domain": "it", "q": "Programming"}))
    assert [c["domain"] for c in it["items"] if c["name"] == "Programming"] == ["it"]
    pharmacy = _body(await client.get(SKILLS, params={"category_id": names["Pharmacy"]["id"], "limit": 100}))
    assert "Pharmacovigilance" in {s["name"] for s in pharmacy["items"]}


@pytest.mark.asyncio
async def test_manager_creates_and_moves_a_category_between_domains_with_an_audit_row(client, db_session):
    manager = await as_role(client, db_session, "placement_manager", "global")
    name = f"Logistics {uuid.uuid4().hex[:6]}"
    created = await client.post(CATS, json={"name": name, "domain": "non_it"})
    assert created.status_code == 201, created.text
    assert created.json()["domain"] == "non_it"
    plain = await client.post(CATS, json={"name": f"{name} B"})
    assert plain.json()["domain"] == "it"  # T4: the default
    moved = await client.patch(f"{CATS}/{created.json()['id']}", json={"domain": "it"})
    assert moved.status_code == 200 and moved.json()["domain"] == "it"
    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.user_id == manager.id, AuditLog.action == "recruiter.skill_category_update"))).all()
    assert [a.metadata_json["fields"] for a in audit] == [["domain"]]


@pytest.mark.asyncio
async def test_domain_validation_and_roles(client, db_session):
    await as_role(client, db_session, "placement_manager", "global")
    bad = await client.post(CATS, json={"name": f"X {uuid.uuid4().hex[:6]}", "domain": "other"})
    assert bad.status_code == 422 and "Domain" in bad.text
    assert (await client.get(CATS, params={"domain": "other"})).status_code == 422
    category = await db_session.scalar(select(SkillCategory).where(SkillCategory.name == "Sales"))
    assert (await client.patch(f"{CATS}/{category.id}", json={"domain": None})).status_code == 422
    await as_role(client, db_session, "placement_team", "it")
    assert (await client.patch(f"{CATS}/{category.id}", json={"domain": "it"})).status_code == 403


@pytest.mark.asyncio
async def test_skills_domain_filter_counts_a_tag_like_the_category_filter(client, db_session):
    """T4: a skill is in a domain through its primary category or a tag."""
    manager = await as_role(client, db_session, "placement_manager", "global")
    assert manager
    sales = await db_session.scalar(select(SkillCategory.id).where(SkillCategory.name == "Sales"))
    programming = await db_session.scalar(select(SkillCategory.id).where(SkillCategory.name == "Programming"))
    tag = uuid.uuid4().hex[:6]
    crm = await client.post(SKILLS, json={"name": f"Salesforce CRM {tag}", "category_id": str(programming), "tag_category_ids": [str(sales)]})
    plain = await client.post(SKILLS, json={"name": f"Rust {tag}", "category_id": str(programming)})
    assert crm.status_code == plain.status_code == 201
    non_it = {s["name"] for s in _body(await client.get(SKILLS, params={"domain": "non_it", "q": tag}))["items"]}
    it = {s["name"] for s in _body(await client.get(SKILLS, params={"domain": "it", "q": tag}))["items"]}
    assert non_it == {f"Salesforce CRM {tag}"} and it == {f"Salesforce CRM {tag}", f"Rust {tag}"}


# --- the minimum level (T5-T9, AC2) ------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_job_requires_python_at_intermediate_or_above(client, db_session):
    """AC2: "Python ≥ intermediate" -- set through the weights route, shown on the detail and the criteria, and a beginner no longer
    matches while an intermediate and an expert (through a related skill too) do."""
    w = await _world(client, db_session)
    python = await w.skill("Python")
    cpython = await w.skill("CPython", related=[python])
    job = await w.requirement(required=[(python, 2)], work_mode="remote")
    beginner, middle, expert = (await w.candidate(python), await w.candidate(python), await w.candidate(cpython))
    await _level(db_session, beginner, python, "beginner")
    await _level(db_session, middle, python, "intermediate")
    await _level(db_session, expert, cpython, "expert")
    assert _body(await _matches(client, job))["total"] == 3  # no level yet: any level counts (T5)
    (row,) = await _job_skills(db_session, job)
    saved = await _weights(client, job, [{"id": str(row.id), "weight": 2, "min_level": "intermediate"}])
    assert saved.status_code == 200, saved.text
    assert [s["min_level"] for s in saved.json()["requirement"]["skills"]] == ["intermediate"]
    body = _body(await _matches(client, job))
    assert {item["id"] for item in body["items"]} == {str(middle.id), str(expert.id)} and body["total"] == 2
    assert body["criteria"]["skills"][0]["min_level"] == "intermediate"
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(job.id), AuditLog.action == "recruiter_requirement.weights"))
    assert audit.metadata_json["changes"] == {f"{python.name} minimum level": [None, "intermediate"]}


@pytest.mark.asyncio
async def test_a_preferred_skill_level_scores_only_at_that_level(client, db_session):
    w = await _world(client, db_session)
    java, aws = await w.skill("Java"), await w.skill("AWS")
    job = await w.requirement(required=[(java, 2)], preferred=[(aws, 2)], work_mode="remote")
    low = await w.candidate(java, aws)
    await _level(db_session, low, aws, "beginner")
    rows = await _job_skills(db_session, job)
    await _weights(client, job, [{"id": str(rows[1].id), "weight": 2, "min_level": "advanced"}])
    item = _body(await _matches(client, job))["items"][0]
    assert item["id"] == str(low.id)  # still a match: the level is on a preferred skill, not a hard filter
    assert [b["matched"] for b in item["breakdown"] if b["kind"] in ("required", "preferred")] == [True, False]  # hrc-018 adds a role item


@pytest.mark.asyncio
async def test_min_level_omitted_keeps_null_clears_and_free_text_is_refused(client, db_session):
    w = await _world(client, db_session)
    java = await w.skill("Java")
    job = await w.requirement(required=[(java, 2)], unresolved=["Cobol"])
    mine, free = await _job_skills(db_session, job)
    assert (await _weights(client, job, [{"id": str(mine.id), "weight": 2, "min_level": "advanced"}])).status_code == 200
    assert (await _weights(client, job, [{"id": str(mine.id), "weight": 4}])).status_code == 200
    assert [(s.weight, s.min_level) for s in await _job_skills(db_session, job)][0] == (4, "advanced")  # omitted = unchanged
    refused = await _weights(client, job, [{"id": str(free.id), "weight": 2, "min_level": "beginner"}])
    assert refused.status_code == 422 and "Skills Master" in refused.text
    assert (await _weights(client, job, [{"id": str(mine.id), "weight": 4, "min_level": "guru"}])).status_code == 422
    assert (await _weights(client, job, [{"id": str(mine.id), "weight": 4, "min_level": None}])).status_code == 200
    assert (await _job_skills(db_session, job))[0].min_level is None


@pytest.mark.asyncio
async def test_editing_the_skill_lists_keeps_a_kept_skills_level(client, db_session):
    """T7: the requirement form's PATCH updates rows in place by name -- the kept skill keeps its level, a removed one is gone."""
    w = await _world(client, db_session)
    java, aws = await w.skill("Java"), await w.skill("AWS")
    job = await w.requirement(required=[(java, 2)], preferred=[(aws, 1)])
    rows = await _job_skills(db_session, job)
    await _weights(client, job, [{"id": str(rows[0].id), "weight": 2, "min_level": "expert"}, {"id": str(rows[1].id), "weight": 1, "min_level": "beginner"}])
    detail = _body(await client.get(f"{REQ}/{job.id}"))
    stamp = detail.get("requirement", detail)["updated_at"]
    edited = await client.patch(f"{REQ}/{job.id}", json={"required_skills": [java.name], "preferred_skills": [], "expected_updated_at": stamp})
    assert edited.status_code == 200, edited.text
    assert [(s["name"], s["min_level"]) for s in edited.json()["requirement"]["skills"]] == [(java.name, "expert")]
