"""rec-016 -- requirement → candidate matching + weighted match score (DEC-SCOPE-157 M1-M8; AC1-AC3). The shared test database is never
truncated, so every test makes its own skills (unique names): only its own candidates can ever hold them."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, Candidate, CandidateSkill, Company, Job, JobApplication, JobSkill, RecCandidateSource, Skill, SkillCategory, SkillRelated
from app.services import candidates as candidate_svc
from app.services import matching
from tests.rec001_helpers import as_role, login, make_pm, make_recruiter, make_user

REQ = "/api/v1/recruiter/requirements"


# --- the pure scoring function (M1, M2; AC1, AC2) -------------------------------------------------------------------------------------
def test_allocate_the_source_example_gives_whole_points_that_total_100():
    skills, experience, location = matching.allocate([30, 25, 15, 10, 10], experience=True, location=False)
    assert skills == [30, 25, 15, 10, 10] and experience == 10 and location == 0
    assert sum(skills) + experience + location == 100


@pytest.mark.parametrize(
    ("weights", "experience", "location"),
    [([2, 2, 2], True, True), ([1], False, False), ([3, 3, 3], False, True), ([2, 1, 1, 1, 1, 1, 1], True, False), ([10, 1], False, False)],
)
def test_allocate_always_totals_exactly_100(weights, experience, location):
    skills, exp, loc = matching.allocate(weights, experience=experience, location=location)
    assert all(isinstance(p, int) and p >= 0 for p in [*skills, exp, loc])
    assert sum(skills) + exp + loc == 100
    assert exp == (10 if experience else 0) and loc == (10 if location else 0)


def test_allocate_largest_remainder_goes_to_the_earliest_on_a_tie():
    assert matching.allocate([1, 1, 1], experience=False, location=False)[0] == [34, 33, 33]
    assert matching.allocate([2, 2, 2], experience=True, location=True)[0] == [27, 27, 26]


def test_allocate_a_zero_weight_skill_earns_nothing():
    """A skill not in the Skills Master is passed as weight 0 (M3)."""
    skills, exp, _ = matching.allocate([2, 0, 2], experience=True, location=False)
    assert skills == [45, 0, 45] and exp == 10


# --- fixtures ------------------------------------------------------------------------------------------------------------------------
class World:
    def __init__(self, db, recruiter):
        self.db, self.recruiter, self.tag = db, recruiter, uuid.uuid4().hex[:8]

    async def skill(self, name, *, related=()) -> Skill:
        category = await self.db.scalar(select(SkillCategory.id).where(SkillCategory.name == "Programming"))
        skill = Skill(name=f"{name} {self.tag}", category_id=category)
        self.db.add(skill)
        await self.db.flush()
        for other in related:
            self.db.add(SkillRelated(skill_a_id=min(skill.id, other.id), skill_b_id=max(skill.id, other.id)))
        await self.db.commit()
        return skill

    async def requirement(self, *, required=(), preferred=(), unresolved=(), status="requirement_received", **fields) -> Job:
        """`required` / `preferred`: (skill, weight) pairs; `unresolved`: free-text required names (skill_id NULL)."""
        company = Company(name=f"Match Co {self.tag} {uuid.uuid4().hex[:4]}", assigned_recruiter_user_id=self.recruiter.id)
        self.db.add(company)
        await self.db.flush()
        job = Job(company_id=company.id, title=f"Java Developer {self.tag}", location=fields.pop("location", "Hyderabad"), description="",
                  skills=[], status=status, assigned_recruiter_user_id=self.recruiter.id, **fields)
        self.db.add(job)
        await self.db.flush()
        position = 0
        for kind, items in (("required", required), ("preferred", preferred)):
            for skill, weight in items:
                self.db.add(JobSkill(job_id=job.id, skill_id=skill.id, name=skill.name, kind=kind, weight=weight, position=position))
                position += 1
        for name in unresolved:
            self.db.add(JobSkill(job_id=job.id, skill_id=None, name=f"{name} {self.tag}", kind="required", weight=2, position=position))
            position += 1
        await self.db.commit()
        return job

    async def candidate(self, *skills, name=None, archived=False, user_id=None, opted_in=False, **fields) -> Candidate:
        source = await self.db.scalar(select(RecCandidateSource.id).where(func.lower(RecCandidateSource.name) == "referral"))
        candidate = Candidate(
            candidate_code=await candidate_svc.next_code(self.db), name=name or f"Cand {uuid.uuid4().hex[:6]}", email=f"m{uuid.uuid4().hex[:12]}@example.com",
            source_id=source, created_by_user_id=self.recruiter.id, user_id=user_id, opted_in=opted_in,
            preferred_locations=fields.pop("preferred_locations", []), **fields,
        )
        if archived:
            candidate.archived_at = datetime.now(UTC)
        self.db.add(candidate)
        await self.db.flush()
        for skill in skills:
            self.db.add(CandidateSkill(candidate_id=candidate.id, skill_id=skill.id, level="advanced", added_by_user_id=self.recruiter.id, status="claimed"))
        await self.db.commit()
        return candidate


async def _world(client, db) -> World:
    manager = await make_pm(db)
    recruiter = await make_recruiter(db, manager)
    await login(client, recruiter)
    world = World(db, recruiter)
    world.manager = manager
    return world


async def _matches(client, job, **params):
    return await client.get(f"{REQ}/{job.id}/matches", params=params)


def _body(response) -> dict:
    assert response.status_code == 200, response.text
    return response.json()


def _row(body, candidate) -> dict:
    return next(item for item in body["items"] if item["id"] == str(candidate.id))


# --- the source's Java example (positive scenario; AC1, AC2) ----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_source_java_requirement_ranks_rahul_first_and_a_full_match_scores_100(client, db_session):
    w = await _world(client, db_session)
    java, spring, sql, micro, aws = [await w.skill(n) for n in ("Java", "Spring Boot", "SQL", "Microservices", "AWS")]
    job = await w.requirement(required=[(java, 3), (spring, 3), (sql, 2)], preferred=[(micro, 1), (aws, 1)],
                              experience_min_months=0, experience_max_months=36, work_mode="remote")
    rahul = await w.candidate(java, spring, sql, micro, aws, name=f"Rahul {w.tag}", experience_months=24)
    priya = await w.candidate(java, spring, sql, name=f"Priya {w.tag}", experience_months=24)
    await w.candidate(java, spring, name=f"Arun {w.tag}", experience_months=24)  # lacks required SQL: filtered out (M4)
    body = _body(await _matches(client, job))
    assert [item["id"] for item in body["items"]] == [str(rahul.id), str(priya.id)] and body["total"] == 2
    top = body["items"][0]
    assert top["score"] == 100  # AC1
    assert sum(b["points"] for b in top["breakdown"]) == top["score"]  # AC2
    assert sum(b["points"] for b in body["items"][1]["breakdown"]) == body["items"][1]["score"] < 100
    assert body["criteria"]["location"] is None  # remote: location does not apply (M6)
    assert body["criteria"]["experience"]["points"] == 10
    assert sum(s["points"] for s in body["criteria"]["skills"]) + 10 == 100
    assert {"email", "mobile", "phone"}.isdisjoint(top)  # R8: no contact details on a match row
    assert body["reason"] is None and body["can_shortlist"] is True and body["can_edit_weights"] is True


@pytest.mark.asyncio
async def test_breakdown_marks_each_item_and_sums_to_the_score(client, db_session):
    w = await _world(client, db_session)
    java, aws = await w.skill("Java"), await w.skill("AWS")
    job = await w.requirement(required=[(java, 2)], preferred=[(aws, 2)], experience_min_months=12, location=" hyderabad ")
    candidate = await w.candidate(java, experience_months=6, location="Hyderabad")
    row = _row(_body(await _matches(client, job)), candidate)
    by_key = {b["key"]: b for b in row["breakdown"]}
    assert by_key["experience"] == {"key": "experience", "label": "Experience", "kind": "experience", "points": 0, "max": 10, "matched": False}
    assert by_key["location"]["matched"] is True and by_key["location"]["points"] == 10
    skills = [b for b in row["breakdown"] if b["kind"] in ("required", "preferred")]
    assert [(b["label"], b["matched"], b["points"], b["max"]) for b in skills] == [(java.name, True, 40, 40), (aws.name, False, 0, 40)]
    assert row["score"] == 50 == sum(b["points"] for b in row["breakdown"])


# --- which candidates appear (M3, M4, M8) -----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_related_skill_counts_and_a_skill_not_in_the_master_is_unused(client, db_session):
    w = await _world(client, db_session)
    core = await w.skill("CoreJ")
    java = await w.skill("Java", related=[core])
    job = await w.requirement(required=[(java, 2)], unresolved=["Weblogic"], work_mode="remote")
    holder = await w.candidate(core)
    body = _body(await _matches(client, job))
    row = _row(body, holder)
    assert row["score"] == 100  # the free-text skill neither filters nor costs points
    unused = [s for s in body["criteria"]["skills"] if not s["in_master"]]
    assert [(s["name"], s["points"]) for s in unused] == [(f"Weblogic {w.tag}", 0)]


@pytest.mark.asyncio
async def test_with_only_preferred_skills_a_candidate_needs_one_of_them(client, db_session):
    w = await _world(client, db_session)
    aws, gcp = await w.skill("AWS"), await w.skill("GCP")
    job = await w.requirement(preferred=[(aws, 1), (gcp, 1)], work_mode="remote")
    one = await w.candidate(gcp)
    both = await w.candidate(aws, gcp)
    body = _body(await _matches(client, job))
    assert [item["id"] for item in body["items"]] == [str(both.id), str(one.id)]
    assert [item["score"] for item in body["items"]] == [100, 50]


@pytest.mark.asyncio
async def test_a_requirement_without_skills_master_skills_explains_itself(client, db_session):
    w = await _world(client, db_session)
    for job in (await w.requirement(), await w.requirement(unresolved=["Weblogic"])):
        body = _body(await _matches(client, job))
        assert body["reason"] == "no_skills" and body["items"] == [] and body["total"] == 0


@pytest.mark.asyncio
async def test_pool_archived_and_not_opted_in_students_are_excluded(client, db_session):
    w = await _world(client, db_session)
    java = await w.skill("Java")
    job = await w.requirement(required=[(java, 2)])
    student = await make_user(db_session, "it_student", "it")
    opted = await make_user(db_session, "it_student", "it")
    keep = await w.candidate(java)
    await w.candidate(java, archived=True)
    await w.candidate(java, user_id=student.id, opted_in=False)
    joined_pool = await w.candidate(java, user_id=opted.id, opted_in=True)
    assert {item["id"] for item in _body(await _matches(client, job))["items"]} == {str(keep.id), str(joined_pool.id)}


@pytest.mark.asyncio
async def test_experience_and_location_fit(client, db_session):
    w = await _world(client, db_session)
    java = await w.skill("Java")
    job = await w.requirement(required=[(java, 2)], experience_min_months=12, experience_max_months=24, location="Pune")
    inside = await w.candidate(java, experience_months=24, preferred_locations=["Mumbai", " PUNE"])
    outside = await w.candidate(java, experience_months=30, location="Delhi")
    unknown = await w.candidate(java)
    body = _body(await _matches(client, job))
    assert [_row(body, c)["score"] for c in (inside, outside, unknown)] == [100, 80, 80]
    assert body["items"][0]["id"] == str(inside.id)
    assert body["criteria"]["experience"] == {"min_months": 12, "max_months": 24, "points": 10}
    assert body["criteria"]["location"] == {"value": "Pune", "points": 10}


@pytest.mark.asyncio
async def test_status_on_this_requirement_is_shown_including_rejected(client, db_session):
    w = await _world(client, db_session)
    java = await w.skill("Java")
    job = await w.requirement(required=[(java, 2)])
    rejected = await w.candidate(java)
    fresh = await w.candidate(java)
    added = await client.post(f"{REQ}/{job.id}/candidates", json={"candidate_id": str(rejected.id), "status": "sourced"})
    assert added.status_code == 201, added.text
    moved = await client.post(f"/api/v1/recruiter/applications/{added.json()['application']['id']}/status", json={"status": "rejected"})
    assert moved.status_code == 200, moved.text
    body = _body(await _matches(client, job))
    assert _row(body, rejected)["application"]["status"] == "rejected" and _row(body, rejected)["application"]["status_label"] == "Rejected"
    assert _row(body, fresh)["application"] is None


@pytest.mark.asyncio
async def test_paging(client, db_session):
    w = await _world(client, db_session)
    java = await w.skill("Java")
    job = await w.requirement(required=[(java, 2)])
    for _ in range(3):
        await w.candidate(java)
    first, second = _body(await _matches(client, job, limit=2)), _body(await _matches(client, job, limit=2, offset=2))
    assert first["total"] == second["total"] == 3 and len(first["items"]) == 2 and len(second["items"]) == 1
    assert not {i["id"] for i in first["items"]} & {i["id"] for i in second["items"]}
    assert (await _matches(client, job, limit=0)).status_code == 422


# --- roles and scope (M7) ---------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_roles_and_scope(client, db_session):
    w = await _world(client, db_session)
    java = await w.skill("Java")
    job = await w.requirement(required=[(java, 2)])
    await w.candidate(java)
    await login(client, w.manager)
    body = _body(await _matches(client, job))
    assert body["total"] == 1 and body["can_shortlist"] is False and body["can_edit_weights"] is False
    await as_role(client, db_session, "super_admin", "it")
    assert _body(await _matches(client, job))["can_shortlist"] is True
    for role, division in (("bdm", "it"), ("hr_team", "it")):
        await as_role(client, db_session, role, division)
        assert (await _matches(client, job)).status_code == 403
    await login(client, await make_recruiter(db_session, w.manager))  # same team, not this requirement's recruiter
    assert (await _matches(client, job)).status_code == 404
    await login(client, w.recruiter)
    assert (await client.get(f"{REQ}/{uuid.uuid4()}/matches")).status_code == 404


@pytest.mark.asyncio
async def test_the_requirement_says_who_can_view_matches(client, db_session):
    """QA-01: the assigned BDM reads the requirement (R10) but not the candidate pool, so the page leaves Matching out."""
    w = await _world(client, db_session)
    job = await w.requirement()
    assert (await client.get(f"{REQ}/{job.id}")).json()["requirement"]["permissions"]["can_view_matches"] is True
    bdm = await make_user(db_session, "bdm", "it")
    company = await db_session.get(Company, job.company_id)
    company.assigned_bdm_user_id = bdm.id
    await db_session.commit()
    await login(client, bdm)
    response = await client.get(f"{REQ}/{job.id}")
    assert response.status_code == 200 and response.json()["requirement"]["permissions"]["can_view_matches"] is False
    assert (await _matches(client, job)).status_code == 403
    await login(client, w.manager)
    assert (await client.get(f"{REQ}/{job.id}")).json()["requirement"]["permissions"]["can_view_matches"] is True


@pytest.mark.asyncio
async def test_a_closed_requirement_still_matches_but_cannot_shortlist(client, db_session):
    w = await _world(client, db_session)
    java = await w.skill("Java")
    job = await w.requirement(required=[(java, 2)], status="closed")
    await w.candidate(java)
    body = _body(await _matches(client, job))
    assert body["total"] == 1 and body["can_shortlist"] is False and body["can_edit_weights"] is True


@pytest.mark.asyncio
async def test_shortlist_creates_exactly_one_application(client, db_session):
    """AC3: Shortlist is rec-017's add at Shortlisted; a second one is a 409 and the match row then carries the status."""
    w = await _world(client, db_session)
    java = await w.skill("Java")
    job = await w.requirement(required=[(java, 2)])
    candidate = await w.candidate(java)
    payload = {"candidate_id": str(candidate.id), "status": "shortlisted"}
    assert (await client.post(f"{REQ}/{job.id}/candidates", json=payload)).status_code == 201
    assert (await client.post(f"{REQ}/{job.id}/candidates", json=payload)).status_code == 409
    count = await db_session.scalar(select(func.count()).select_from(JobApplication).where(JobApplication.job_id == job.id, JobApplication.candidate_id == candidate.id))
    assert count == 1
    assert _row(_body(await _matches(client, job)), candidate)["application"]["status"] == "shortlisted"


# --- weights (M1) -----------------------------------------------------------------------------------------------------------------------
async def _weights(client, job, weights):
    return await client.put(f"{REQ}/{job.id}/skill-weights", json={"weights": weights})


async def _job_skills(db, job) -> list[JobSkill]:
    stmt = select(JobSkill).where(JobSkill.job_id == job.id).order_by(JobSkill.position).execution_options(populate_existing=True)
    return list((await db.scalars(stmt)).all())


@pytest.mark.asyncio
async def test_weights_change_the_score_and_are_audited(client, db_session):
    w = await _world(client, db_session)
    java, aws = await w.skill("Java"), await w.skill("AWS")
    job = await w.requirement(required=[(java, 2)], preferred=[(aws, 2)], work_mode="remote")
    candidate = await w.candidate(java)
    assert _row(_body(await _matches(client, job)), candidate)["score"] == 50
    java_row, aws_row = await _job_skills(db_session, job)
    response = await _weights(client, job, [{"id": str(java_row.id), "weight": 9}, {"id": str(aws_row.id), "weight": 1}])
    assert response.status_code == 200, response.text
    assert [s["weight"] for s in response.json()["requirement"]["skills"]] == [9, 1]
    assert _row(_body(await _matches(client, job)), candidate)["score"] == 90
    audits = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == str(job.id), AuditLog.action == "recruiter_requirement.weights"))).all()
    assert len(audits) == 1 and audits[0].metadata_json == {"skills": sorted([str(java_row.id), str(aws_row.id)])}
    again = await _weights(client, job, [{"id": str(java_row.id), "weight": 9}])  # unchanged: nothing written
    assert again.status_code == 200
    assert await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == str(job.id), AuditLog.action == "recruiter_requirement.weights")) == 1


@pytest.mark.asyncio
async def test_weights_validation(client, db_session):
    w = await _world(client, db_session)
    java = await w.skill("Java")
    job = await w.requirement(required=[(java, 2)])
    other = await w.requirement(required=[(java, 2)])
    (mine,), (theirs,) = await _job_skills(db_session, job), await _job_skills(db_session, other)
    for weights in ([{"id": str(mine.id), "weight": 0}], [{"id": str(mine.id), "weight": 11}], [], [{"id": str(mine.id), "weight": 2}] * 2,
                    [{"id": str(theirs.id), "weight": 2}], [{"id": str(mine.id)}]):
        assert (await _weights(client, job, weights)).status_code == 422, weights
    assert (await client.put(f"{REQ}/{job.id}/skill-weights", json={"weights": [{"id": str(mine.id), "weight": 3}], "x": 1})).status_code == 422
    assert [s.weight for s in await _job_skills(db_session, job)] == [2]


@pytest.mark.asyncio
async def test_weights_roles_and_state(client, db_session):
    w = await _world(client, db_session)
    java = await w.skill("Java")
    job = await w.requirement(required=[(java, 2)])
    (row,) = await _job_skills(db_session, job)
    body = [{"id": str(row.id), "weight": 5}]
    await login(client, w.manager)
    assert (await _weights(client, job, body)).status_code == 403
    await as_role(client, db_session, "bdm", "it")
    assert (await _weights(client, job, body)).status_code in (403, 404)
    await login(client, w.recruiter)
    cancelled = await w.requirement(required=[(java, 2)], status="cancelled")
    (cancelled_row,) = await _job_skills(db_session, cancelled)
    assert (await _weights(client, cancelled, [{"id": str(cancelled_row.id), "weight": 5}])).status_code == 409
    assert (await _weights(client, job, body)).status_code == 200
