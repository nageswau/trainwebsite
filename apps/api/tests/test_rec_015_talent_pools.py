"""rec-015 -- talent pools (spec §1-§3; DEC-SCOPE-159 P1-P8): a manager-defined rule (a rec-013 expression + an experience band) whose
members are computed on read. The shared test database is never truncated, so each test makes its own skills (unique names) and asserts
only on its own candidates."""

import uuid

import pytest
from sqlalchemy import select

from app.models import CandidateSkill, Skill, TalentPool
from tests.rec001_helpers import as_role, login, make_pm, make_recruiter
from tests.test_rec_013_find_candidates import _world

POOLS = "/api/v1/recruiter/pools"


def _members(client, pool_id, **params):
    return client.get(f"{POOLS}/{pool_id}/candidates", params=params)


async def _ids(response) -> set[str]:
    assert response.status_code == 200, response.text
    return {item["id"] for item in response.json()["items"]}


async def _create(client, **body):
    body.setdefault("name", f"Pool {uuid.uuid4().hex[:8]}")
    return await client.post(POOLS, json=body)


async def _pool(client, **body) -> dict:
    response = await _create(client, **body)
    assert response.status_code == 201, response.text
    return response.json()


# --- positive scenario: the manager creates "Cloud Engineers" (AWS OR Azure OR GCP) --------------------------------------------------
@pytest.mark.asyncio
async def test_manager_creates_an_or_pool_and_its_members_are_computed(client, db_session):
    w = await _world(client, db_session, "pm")
    aws, azure, gcp, cobol = await w.skill("AWS"), await w.skill("Azure"), await w.skill("GCP"), await w.skill("Cobol")
    a, b = await w.candidate(aws), await w.candidate(gcp, azure)
    await w.candidate(cobol)
    pool = await _pool(client, name=f"Cloud Engineers {w.tag}", any=[[aws.name, azure.name, gcp.name]])
    assert pool["any"] == [[aws.name, azure.name, gcp.name]] and pool["all"] == [] and pool["active"] is True
    assert pool["members"] == 2 and pool["unavailable"] == [] and pool["created_by"]["id"] == str(w.actor.id)
    response = await _members(client, pool["id"])
    assert await _ids(response) == {str(a.id), str(b.id)}
    body = response.json()
    assert body["total"] == 2 and body["pool"]["id"] == pool["id"] and len(body["terms"]) == 3 and body["can_manage"] is True
    assert [s["matched"] for s in body["items"][0]["skills"]] == [True] * len(body["items"][0]["skills"])
    listed = {p["id"]: p for p in (await client.get(POOLS)).json()["items"]}
    assert listed[pool["id"]]["members"] == 2


# --- AC1: adding a Java skill places a candidate in "Java Developers" with no other action ---------------------------------------------
@pytest.mark.asyncio
async def test_adding_the_skill_places_the_candidate_in_the_pool(client, db_session):
    w = await _world(client, db_session, "pm")
    java = await w.skill("Java", aliases=["J2EE"])
    candidate = await w.candidate()
    pool = await _pool(client, all=[f"j2ee {w.tag}"])
    assert pool["all"] == [java.name]  # an alias is saved as its skill
    assert str(candidate.id) not in await _ids(await _members(client, pool["id"]))
    db_session.add(CandidateSkill(candidate_id=candidate.id, skill_id=java.id, level="beginner", added_by_user_id=w.actor.id, status="claimed"))
    await db_session.commit()
    assert await _ids(await _members(client, pool["id"])) == {str(candidate.id)}


# --- AC2: Freshers = 0 years (0-11 months); Experienced = 12+ months -----------------------------------------------------------------
@pytest.mark.asyncio
async def test_experience_band_decides_membership(client, db_session):
    w = await _world(client, db_session, "pm")
    python = await w.skill("Python")
    fresher, junior, unknown = await w.candidate(python, experience_months=0), await w.candidate(python, experience_months=12), await w.candidate(python)
    freshers = await _pool(client, all=[python.name], experience_max_months=11)
    experienced = await _pool(client, all=[python.name], experience_min_months=12)
    assert await _ids(await _members(client, freshers["id"])) == {str(fresher.id)}
    assert await _ids(await _members(client, experienced["id"])) == {str(junior.id)}
    assert str(unknown.id) not in await _ids(await _members(client, experienced["id"]))
    # a pool may be an experience band alone: the newest candidates come first, so ours are on the first page
    band = await _pool(client, experience_max_months=11)
    page = await _ids(await _members(client, band["id"]))
    assert str(fresher.id) in page and str(junior.id) not in page and str(unknown.id) not in page


@pytest.mark.asyncio
async def test_the_seeded_example_pools(client, db_session):
    await login(client, await make_pm(db_session))
    seeded = {p.name: p for p in (await db_session.scalars(select(TalentPool).where(TalentPool.created_by_user_id.is_(None)))).all()}
    assert {"Java Developers", "Python Developers", "Full Stack Developers", "Cloud Engineers", "Freshers", "Experienced Professionals"} <= set(seeded)
    assert (seeded["Freshers"].experience_min_months, seeded["Freshers"].experience_max_months) == (None, 11)
    assert (seeded["Experienced Professionals"].experience_min_months, seeded["Experienced Professionals"].experience_max_months) == (12, None)
    assert seeded["Java Developers"].all_terms == ["Java"] and seeded["Cloud Engineers"].any_terms == [["AWS", "Azure", "GCP"]]


# --- negative: an invalid expression is a 422 ------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    {"all": ["no such skill zzq"]},
    {},
    {"all": [], "any": []},
    {"experience_min_months": 24, "experience_max_months": 12},
    {"any": [[]]},
    {"experience_max_months": 601},
    {"name": "  "},
    {"all": ["x"], "unexpected": 1},
])
async def test_an_invalid_pool_is_a_422(client, db_session, body):
    await login(client, await make_pm(db_session))
    response = await client.post(POOLS, json={"name": f"Bad {uuid.uuid4().hex[:8]}", **body})
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_an_unknown_skill_names_suggestions(client, db_session):
    w = await _world(client, db_session, "pm")
    await w.skill("Kotlin")
    response = await _create(client, all=[f"kot {w.tag}x"])
    assert response.status_code == 422 and response.json()["detail"]["code"] == "unknown_skill"


@pytest.mark.asyncio
async def test_a_duplicate_name_is_a_409_ignoring_case(client, db_session):
    w = await _world(client, db_session, "pm")
    java = await w.skill("Java")
    await _pool(client, name=f"Dup {w.tag}", all=[java.name])
    assert (await _create(client, name=f"DUP {w.tag}", all=[java.name])).status_code == 409


# --- edge: a pool whose skill was deactivated ------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_deactivated_skill_is_unavailable_and_matches_nobody(client, db_session):
    w = await _world(client, db_session, "pm")
    java, aws, azure = await w.skill("Java"), await w.skill("AWS"), await w.skill("Azure")
    await w.candidate(java, aws)  # loses the OR group once AWS is inactive
    only_azure = await w.candidate(java, azure)
    and_pool = await _pool(client, all=[java.name])
    or_pool = await _pool(client, all=[java.name], any=[[aws.name, azure.name]])
    skill = await db_session.get(Skill, aws.id)
    skill.active = False
    await db_session.commit()
    response = await _members(client, or_pool["id"])
    assert await _ids(response) == {str(only_azure.id)}  # the OR group keeps Azure
    assert response.json()["pool"]["unavailable"] == [aws.name]
    db_java = await db_session.get(Skill, java.id)
    db_java.active = False
    await db_session.commit()
    response = await _members(client, and_pool["id"])
    assert response.json()["items"] == [] and response.json()["total"] == 0 and response.json()["pool"]["unavailable"] == [java.name]
    listed = {p["id"]: p for p in (await client.get(POOLS)).json()["items"]}
    assert listed[and_pool["id"]]["members"] == 0 and listed[and_pool["id"]]["unavailable"] == [java.name]


# --- PATCH ---------------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_patch_renames_changes_the_rule_and_deactivates(client, db_session):
    w = await _world(client, db_session, "pm")
    java, python = await w.skill("Java"), await w.skill("Python")
    py = await w.candidate(python)
    pool = await _pool(client, all=[java.name])
    response = await client.patch(f"{POOLS}/{pool['id']}", json={"name": f"Renamed {w.tag}", "all": [python.name]})
    assert response.status_code == 200, response.text
    assert response.json()["name"] == f"Renamed {w.tag}" and response.json()["members"] == 1
    assert await _ids(await _members(client, pool["id"])) == {str(py.id)}
    # the merged rule is re-validated: no skill and no band left
    assert (await client.patch(f"{POOLS}/{pool['id']}", json={"all": []})).status_code == 422
    assert (await client.patch(f"{POOLS}/{pool['id']}", json={"active": False})).json()["active"] is False
    assert (await client.patch(f"{POOLS}/{uuid.uuid4()}", json={"active": True})).status_code == 404


# --- roles (P6) ----------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_recruiters_read_active_pools_and_managers_write(client, db_session):
    w = await _world(client, db_session, "pm")
    java = await w.skill("Java")
    live = await _pool(client, all=[java.name])
    hidden = await _pool(client, all=[java.name], active=False)
    listed = (await client.get(POOLS, params={"include_inactive": "true"})).json()
    assert listed["can_manage"] is True and {live["id"], hidden["id"]} <= {p["id"] for p in listed["items"]}
    assert (await _members(client, hidden["id"])).status_code == 200

    await login(client, await make_recruiter(db_session))
    listed = (await client.get(POOLS, params={"include_inactive": "true"})).json()
    ids = {p["id"] for p in listed["items"]}
    assert listed["can_manage"] is False and live["id"] in ids and hidden["id"] not in ids
    assert (await _members(client, live["id"])).json()["can_manage"] is False
    assert (await _members(client, hidden["id"])).status_code == 404
    assert (await _create(client, all=[java.name])).status_code == 403
    assert (await client.patch(f"{POOLS}/{live['id']}", json={"active": False})).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("role, division, status", [("hr_team", "it", 200), ("bdm", "it", 403), ("employer", "it", 403)])
async def test_other_roles(client, db_session, role, division, status):
    await as_role(client, db_session, role, division)
    assert (await client.get(POOLS)).status_code == status
    assert (await _create(client, all=["Java"])).status_code == 403


# --- the pool (R11): archived and not-opted-in candidates are never members -------------------------------------------------------------
@pytest.mark.asyncio
async def test_archived_and_not_opted_in_candidates_are_excluded(client, db_session):
    w = await _world(client, db_session, "pm")
    java = await w.skill("Java")
    student = await as_role(client, db_session, "it_student", "it")
    await login(client, w.actor)
    kept = await w.candidate(java)
    await w.candidate(java, archived=True)
    await w.candidate(java, user_id=student.id, opted_in=False)
    pool = await _pool(client, all=[java.name])
    assert await _ids(await _members(client, pool["id"])) == {str(kept.id)} and pool["members"] == 1
