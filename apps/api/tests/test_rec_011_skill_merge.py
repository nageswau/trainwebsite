"""rec-011 -- the skill merge rec-006 S1 moved here (spec §5, DEC-SCOPE-135 SK7, AC6): merging A into B re-points candidate skills (the
stronger status wins a clash) and requirement skills, moves aliases and related links, deletes A and makes A's name an alias of B. Every
skill and candidate is created by the test (the shared database is never truncated)."""

import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog, CandidateSkill, Job, JobSkill, Skill
from app.services.skills import resolve
from tests.rec001_helpers import login, make_pm, make_recruiter
from tests.test_rec_011_candidate_skills import _candidate, skills_url

SKILLS = "/api/v1/recruiter/skills"


async def _skill(client, db, prefix: str) -> dict:
    category_id = str(await db.scalar(select(Skill.category_id).where(Skill.name == "Java")))
    response = await client.post(SKILLS, json={"name": f"{prefix} {uuid.uuid4().hex[:6]}", "category_id": category_id})
    assert response.status_code == 201, response.text
    return response.json()


async def _give(client, candidate, skill, status=None) -> dict:
    response = await client.post(skills_url(candidate["id"]), json={"skill": skill["name"], "level": "advanced"})
    assert response.status_code == 201, response.text
    item = response.json()
    if status:
        item = (await client.post(skills_url(candidate["id"], f"/{item['id']}/status"), json={"status": status})).json()
    return item


async def _job_skill(client, db, skill) -> JobSkill:
    company = (await client.post("/api/v1/recruiter/companies", json={"name": f"Merge {uuid.uuid4().hex[:8]} Pvt"})).json()["company"]
    job = Job(company_id=uuid.UUID(company["id"]), title="Java Developer", location="Pune", description="-", skills=[skill["name"]])
    db.add(job)
    await db.flush()
    row = JobSkill(job_id=job.id, skill_id=uuid.UUID(skill["id"]), name=skill["name"], kind="required", weight=3, position=0)
    db.add(row)
    await db.commit()
    return row


@pytest.mark.asyncio
async def test_merging_a_into_b_repoints_everything_and_a_name_resolves_to_b(client, db_session):
    manager = await make_pm(db_session)
    await login(client, manager)
    a, b, c = await _skill(client, db_session, "MergeA"), await _skill(client, db_session, "MergeB"), await _skill(client, db_session, "MergeC")
    alias = f"Alias {uuid.uuid4().hex[:6]}"
    assert (await client.post(f"{SKILLS}/{a['id']}/aliases", json={"alias": alias})).status_code == 201
    assert (await client.post(f"{SKILLS}/{a['id']}/related", json={"skill_id": c["id"]})).status_code == 201
    both, only_a = await _candidate(client, db_session), await _candidate(client, db_session)
    kept = await _give(client, both, a, status="verified")  # stronger than B's claimed row -> kept, re-pointed to B
    dropped = await _give(client, both, b)
    moved = await _give(client, only_a, a)
    job_skill = await _job_skill(client, db_session, a)

    response = await client.post(f"{SKILLS}/{a['id']}/merge", json={"into_skill_id": b["id"]})
    assert response.status_code == 200, response.text
    merged = response.json()
    assert merged["id"] == b["id"]
    assert {x["alias"] for x in merged["aliases"]} == {alias, a["name"]}
    assert [r["id"] for r in merged["related"]] == [c["id"]]

    assert (await client.get(f"{SKILLS}/{a['id']}")).status_code == 404
    assert (await resolve(db_session, a["name"])).id == uuid.UUID(b["id"])
    rows = {
        r.candidate_id: r
        for r in (
            await db_session.scalars(select(CandidateSkill).where(CandidateSkill.candidate_id.in_([uuid.UUID(both["id"]), uuid.UUID(only_a["id"])])).execution_options(populate_existing=True))
        ).all()
    }
    assert len(rows) == 2
    assert rows[uuid.UUID(both["id"])].id == uuid.UUID(kept["id"]) and rows[uuid.UUID(both["id"])].skill_id == uuid.UUID(b["id"])
    assert rows[uuid.UUID(both["id"])].status == "verified" and uuid.UUID(dropped["id"]) not in {r.id for r in rows.values()}
    assert rows[uuid.UUID(only_a["id"])].id == uuid.UUID(moved["id"]) and rows[uuid.UUID(only_a["id"])].skill_id == uuid.UUID(b["id"])
    await db_session.refresh(job_skill)
    assert job_skill.skill_id == uuid.UUID(b["id"]) and job_skill.name == a["name"]

    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "recruiter.skill_merge", AuditLog.entity_id == b["id"]))
    assert audit.metadata_json == {
        "merged_skill_id": a["id"],
        "merged_name": a["name"],
        "candidate_skills_moved": 2,
        "candidate_skills_dropped": 1,
        "job_skills_moved": 1,
        "aliases_moved": 1,
    }
    added = await client.post(skills_url(only_a["id"]), json={"skill": a["name"], "level": "beginner"})
    assert added.status_code == 409  # A's name now resolves to B, which the candidate already has


@pytest.mark.asyncio
async def test_on_an_equal_clash_the_target_row_is_kept(client, db_session):
    await login(client, await make_pm(db_session))
    a, b = await _skill(client, db_session, "TieA"), await _skill(client, db_session, "TieB")
    candidate = await _candidate(client, db_session)
    await _give(client, candidate, a)
    target_row = await _give(client, candidate, b)
    assert (await client.post(f"{SKILLS}/{a['id']}/merge", json={"into_skill_id": b["id"]})).status_code == 200
    items = (await client.get(skills_url(candidate["id"]))).json()["items"]
    assert [i["id"] for i in items] == [target_row["id"]]


@pytest.mark.asyncio
async def test_a_merge_with_a_related_link_between_a_and_b_drops_it(client, db_session):
    await login(client, await make_pm(db_session))
    a, b = await _skill(client, db_session, "PairA"), await _skill(client, db_session, "PairB")
    assert (await client.post(f"{SKILLS}/{a['id']}/related", json={"skill_id": b["id"]})).status_code == 201
    response = await client.post(f"{SKILLS}/{a['id']}/merge", json={"into_skill_id": b["id"]})
    assert response.status_code == 200 and response.json()["related"] == []


@pytest.mark.asyncio
async def test_merge_refusals(client, db_session):
    await login(client, await make_pm(db_session))
    a, b = await _skill(client, db_session, "RefA"), await _skill(client, db_session, "RefB")
    merge = f"{SKILLS}/{a['id']}/merge"
    assert (await client.post(merge, json={"into_skill_id": a["id"]})).json()["detail"] == "A skill cannot be merged into itself"
    assert (await client.post(merge, json={"into_skill_id": str(uuid.uuid4())})).json()["detail"] == "Choose an active skill to merge into"
    assert (await client.patch(f"{SKILLS}/{b['id']}", json={"active": False})).status_code == 200
    response = await client.post(merge, json={"into_skill_id": b["id"]})
    assert response.status_code == 422 and response.json()["detail"] == "Choose an active skill to merge into"
    assert (await client.post(f"{SKILLS}/{uuid.uuid4()}/merge", json={"into_skill_id": a["id"]})).status_code == 404
    assert (await client.post(merge, json={})).json()["detail"] == "Merge into is required"
    # an inactive skill can still be merged away
    assert (await client.post(f"{SKILLS}/{b['id']}/merge", json={"into_skill_id": a["id"]})).status_code == 200


@pytest.mark.asyncio
async def test_recruiters_cannot_merge(client, db_session):
    await login(client, await make_pm(db_session))
    a, b = await _skill(client, db_session, "RoleA"), await _skill(client, db_session, "RoleB")
    await login(client, await make_recruiter(db_session))
    assert (await client.post(f"{SKILLS}/{a['id']}/merge", json={"into_skill_id": b["id"]})).status_code == 403
