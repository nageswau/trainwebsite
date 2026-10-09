"""rec-013 -- Find Candidates (spec §1-§4, §6; DEC-SCOPE-142 FS1-FS12): skill AND / OR search expanded through aliases and related skills,
the S2-§18 filters, the F1-F3 facets, the pool, the 422 caps and the roles. The shared test database is never truncated, so every test
makes its own skills (unique names) and only its own candidates can ever hold them."""

import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import event, insert, select

from app.core.database import engine
from app.models import Candidate, CandidateSkill, RecCandidateSource, Skill, SkillAlias, SkillCategory, SkillRelated, User
from app.schemas import CandidateSearch
from app.services import candidate_search
from tests.rec001_helpers import as_role, login, make_pm, make_recruiter, make_user

SEARCH = "/api/v1/recruiter/candidates/search"


class World:
    """One test's skills and candidates, written straight to the database."""

    def __init__(self, db, actor: User, category_id, source_id):
        self.db, self.actor, self.category_id, self.source_id = db, actor, category_id, source_id
        self.tag = uuid.uuid4().hex[:8]

    async def skill(self, name: str, *, aliases=(), related=()) -> Skill:
        skill = Skill(name=f"{name} {self.tag}", category_id=self.category_id)
        self.db.add(skill)
        await self.db.flush()
        for alias in aliases:
            self.db.add(SkillAlias(skill_id=skill.id, alias=f"{alias} {self.tag}"))
        for other in related:
            self.db.add(SkillRelated(skill_a_id=min(skill.id, other.id), skill_b_id=max(skill.id, other.id)))
        await self.db.commit()
        return skill

    async def candidate(self, *skills, verified=(), user_id=None, opted_in=False, archived=False, **fields) -> Candidate:
        candidate = Candidate(
            candidate_code=f"T{uuid.uuid4().hex[:11]}", name=fields.pop("name", f"Cand {uuid.uuid4().hex[:6]}"),
            email=f"c{uuid.uuid4().hex[:12]}@example.com", source_id=fields.pop("source_id", self.source_id), created_by_user_id=self.actor.id,
            user_id=user_id, opted_in=opted_in, **fields,
        )
        if archived:
            candidate.archived_at = datetime.now(UTC)
        self.db.add(candidate)
        await self.db.flush()
        for skill in skills:
            done = skill in verified
            self.db.add(CandidateSkill(
                candidate_id=candidate.id, skill_id=skill.id, level="advanced", added_by_user_id=self.actor.id,
                status="verified" if done else "claimed", verified_at=datetime.now(UTC) if done else None,
                verified_by_user_id=self.actor.id if done else None,
            ))
        await self.db.commit()
        return candidate


async def _world(client, db, role: str = "recruiter") -> World:
    actor = await (make_recruiter(db) if role == "recruiter" else make_pm(db))
    await login(client, actor)
    category = await db.scalar(select(SkillCategory.id).where(SkillCategory.name == "Programming"))
    source = await db.scalar(select(RecCandidateSource.id).where(RecCandidateSource.name == "Referral"))
    return World(db, actor, category, source)


async def _search(client, **body):
    return await client.post(SEARCH, json=body)


def _ids(response) -> set[str]:
    assert response.status_code == 200, response.text
    return {item["id"] for item in response.json()["items"]}


# --- AC1: a skill finds its aliases' and related skills' holders ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_skill_alias_finds_the_holders_and_related_skills_are_included(client, db_session):
    w = await _world(client, db_session)
    core = await w.skill("CoreJ")
    java = await w.skill("Java", aliases=["J2EE"], related=[core])
    other = await w.skill("Cobol")
    a = await w.candidate(java)
    b = await w.candidate(core)
    await w.candidate(other)
    response = await _search(client, all=[f"j2ee {w.tag}"])
    assert _ids(response) == {str(a.id), str(b.id)}
    term = response.json()["terms"][0]
    assert term["term"] == f"j2ee {w.tag}" and term["skill"]["name"] == java.name and term["also"] == [core.name]
    # related reads both ways
    assert _ids(await _search(client, all=[core.name])) == {str(a.id), str(b.id)}


# --- AC2 / AC3: AND, and AND with an OR group ---------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_and_returns_only_candidates_with_every_skill(client, db_session):
    w = await _world(client, db_session)
    java, spring, sql = await w.skill("Java"), await w.skill("Spring"), await w.skill("SQL")
    full = await w.candidate(java, spring, sql)
    await w.candidate(java, spring)
    await w.candidate(java, sql)
    response = await _search(client, all=[java.name, spring.name, sql.name])
    assert _ids(response) == {str(full.id)} and response.json()["total"] == 1


@pytest.mark.asyncio
async def test_and_with_an_or_group(client, db_session):
    w = await _world(client, db_session)
    java, spring, aws, azure = await w.skill("Java"), await w.skill("Spring"), await w.skill("AWS"), await w.skill("Azure")
    with_aws = await w.candidate(java, spring, aws)
    with_azure = await w.candidate(java, spring, azure)
    await w.candidate(java, spring)
    await w.candidate(java, aws)
    assert _ids(await _search(client, all=[java.name, spring.name], any=[[aws.name, azure.name]])) == {str(with_aws.id), str(with_azure.id)}
    # a lone OR group: Java OR AWS
    python = await w.skill("Python")
    py = await w.candidate(python)
    assert str(py.id) in _ids(await _search(client, any=[[java.name, python.name]]))


@pytest.mark.asyncio
async def test_verified_only_needs_a_verified_row_for_each_matched_skill(client, db_session):
    w = await _world(client, db_session)
    java = await w.skill("Java")
    verified = await w.candidate(java, verified=[java])
    await w.candidate(java)
    assert _ids(await _search(client, all=[java.name], verified_only=True)) == {str(verified.id)}


# --- AC4: facets ------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_facet_counts_add_up_to_the_filtered_total(client, db_session):
    w = await _world(client, db_session)
    java = await w.skill("Java")
    rows = [
        dict(experience_months=0, notice_days=0, location="Hyderabad"), dict(experience_months=11, notice_days=15, location="hyderabad"),
        dict(experience_months=12, notice_days=16, location="Bangalore"), dict(experience_months=35, notice_days=30, location="Chennai"),
        dict(experience_months=36, notice_days=31, location="Pune"), dict(experience_months=59, notice_days=59, location="Delhi"),
        dict(experience_months=60, notice_days=60, location="Kochi"), dict(experience_months=None, notice_days=None, location=None),
    ]
    for fields in rows:
        await w.candidate(java, **fields)
    body = (await _search(client, all=[java.name])).json()
    assert body["total"] == 8
    facets = body["facets"]
    assert {f["key"]: f["count"] for f in facets["experience"]} == {"y0_1": 2, "y1_3": 2, "y3_5": 2, "y5_plus": 1, "none": 1}
    assert {f["key"]: f["count"] for f in facets["availability"]} == {"immediate": 1, "d15": 1, "d30": 2, "d31_59": 2, "d60_plus": 1, "none": 1}
    location = facets["location"]
    assert location[0] == {"value": "Hyderabad", "count": 2}
    assert len([f for f in location if f["value"] not in (None, "__other__")]) == 5
    assert sum(f["count"] for f in location) == 8
    assert {f["value"]: f["count"] for f in location}[None] == 1 and {f["value"]: f["count"] for f in location}["__other__"] == 1
    for facet in facets.values():
        assert sum(f["count"] for f in facet) == body["total"]


@pytest.mark.asyncio
async def test_each_filter_narrows(client, db_session):
    w = await _world(client, db_session)
    java = await w.skill("Java")
    other_source = await db_session.scalar(select(RecCandidateSource.id).where(RecCandidateSource.name == "LinkedIn"))
    target = await w.candidate(java, experience_months=30, location="Hyderabad", notice_days=0, qualification="B.Tech CSE",
                               expected_salary=Decimal("800000"), status="available")
    await w.candidate(java, experience_months=80, location="Hyderabad", notice_days=0, qualification="B.Tech", expected_salary=Decimal("800000"))
    await w.candidate(java, experience_months=30, location="Pune", notice_days=0, qualification="B.Tech", expected_salary=Decimal("800000"))
    await w.candidate(java, experience_months=30, location="Hyderabad", notice_days=45, qualification="B.Tech", expected_salary=Decimal("800000"))
    await w.candidate(java, experience_months=30, location="Hyderabad", notice_days=0, qualification="MBA", expected_salary=Decimal("800000"))
    await w.candidate(java, experience_months=30, location="Hyderabad", notice_days=0, qualification="B.Tech", expected_salary=Decimal("1500000"))
    await w.candidate(java, experience_months=30, location="Hyderabad", notice_days=0, qualification="B.Tech", expected_salary=Decimal("800000"),
                      status="placed")
    await w.candidate(java, experience_months=30, location="Hyderabad", notice_days=0, qualification="B.Tech", expected_salary=Decimal("800000"),
                      source_id=other_source)
    response = await _search(
        client, all=[java.name], experience_min_months=24, experience_max_months=60, location="hyder", availability=["immediate", "d15"],
        qualification="b.tech", salary_min=500000, salary_max=1000000, status="available", source_id=str(w.source_id),
    )
    assert _ids(response) == {str(target.id)}
    item = response.json()["items"][0]
    assert item["source"]["name"] == "Referral" and item["skills"] == [{"name": java.name, "level": "advanced", "status": "claimed", "matched": True}]
    assert "email" not in item and "mobile" not in item


# --- AC5: the pool ----------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_non_opted_in_student_and_an_archived_candidate_are_never_returned(client, db_session):
    w = await _world(client, db_session)
    java = await w.skill("Java")
    hidden_user = await make_user(db_session, "it_student", "it")
    shown_user = await make_user(db_session, "it_student", "it")
    hidden = await w.candidate(java, user_id=hidden_user.id, opted_in=False)
    shown = await w.candidate(java, user_id=shown_user.id, opted_in=True)
    external = await w.candidate(java)
    await w.candidate(java, archived=True)
    ids = _ids(await _search(client, all=[java.name]))
    assert ids == {str(shown.id), str(external.id)} and str(hidden.id) not in ids


# --- 422s -------------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("body, needle", [
    ({}, "at least one skill"),
    ({"all": []}, "at least one skill"),
    ({"all": [f"S{i}" for i in range(21)]}, "20 skills"),
    ({"any": [["a"], ["b"], ["c"], ["d"], ["e"], ["f"]]}, "5 groups"),
    ({"all": ["Java"], "experience_min_months": 60, "experience_max_months": 12}, "experience"),
    ({"all": ["Java"], "salary_min": 9, "salary_max": 1}, "salary"),
    ({"all": ["Java"], "availability": ["soon"]}, "vailability"),
    ({"all": ["Java"], "colour": "red"}, ""),
    ({"all": ["   "]}, ""),
])
async def test_bad_bodies_are_422(client, db_session, body, needle):
    await _world(client, db_session)
    response = await client.post(SEARCH, json=body)
    assert response.status_code == 422, response.text
    assert needle.lower() in str(response.json()["detail"]).lower()


@pytest.mark.asyncio
async def test_an_unknown_skill_is_422_with_suggestions(client, db_session):
    w = await _world(client, db_session)
    java = await w.skill("Javelin", aliases=["Jvl"])
    response = await _search(client, all=[w.tag])  # part of the skill's name, not a name or an alias
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "unknown_skill" and detail["term"] == w.tag and detail["suggestions"] == [java.name]
    assert w.tag in detail["message"]


# --- roles ------------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("role, division", [("employer", "it"), ("it_admin", "it"), ("it_student", "it"), ("telecaller", "global")])
async def test_other_roles_are_403(client, db_session, role, division):
    await as_role(client, db_session, role, division)
    response = await client.post(SEARCH, json={"all": ["Java"]})
    assert response.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("role, division", [("hr_team", "it"), ("placement_manager", "global"), ("super_admin", "global")])
async def test_readers_may_search(client, db_session, role, division):
    w = await _world(client, db_session)
    java = await w.skill("Java")
    mine = await w.candidate(java)
    await as_role(client, db_session, role, division)
    assert _ids(await _search(client, all=[java.name])) == {str(mine.id)}


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    assert (await client.post(SEARCH, json={"all": ["Java"]})).status_code == 401


# --- performance ------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_query_count_is_fixed(client, db_session):
    w = await _world(client, db_session)
    java, sql = await w.skill("Java"), await w.skill("SQL")
    await w.candidate(java, sql, location="Hyderabad")
    for i in range(6):
        await w.candidate(java, location=f"Town {i}")
    statements: list[str] = []
    listener = lambda *args: statements.append(args[2])  # noqa: E731 -- (conn, cursor, statement, ...)
    event.listen(engine.sync_engine, "before_cursor_execute", listener)
    try:
        statements.clear()
        assert (await _search(client, all=[java.name, sql.name])).json()["total"] == 1
        one = len([s for s in statements if s.lstrip().upper().startswith("SELECT")])
        statements.clear()
        assert (await _search(client, all=[java.name], any=[[sql.name, java.name]])).json()["total"] == 7
        assert len([s for s in statements if s.lstrip().upper().startswith("SELECT")]) == one
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener)


@pytest.mark.asyncio
async def test_ten_thousand_candidates_search_within_budget(db_session):
    """Spec §6: 10k pool candidates with 3 skills each, written in a transaction that is rolled back, searched in under 2 s."""
    actor = await make_recruiter(db_session)
    category = await db_session.scalar(select(SkillCategory.id).where(SkillCategory.name == "Programming"))
    source = await db_session.scalar(select(RecCandidateSource.id).where(RecCandidateSource.name == "Referral"))
    tag = uuid.uuid4().hex[:8]
    skills = [Skill(id=uuid.uuid4(), name=f"Perf{i} {tag}", category_id=category) for i in range(6)]
    db_session.add_all(skills)
    await db_session.flush()
    try:
        people = [
            {"id": uuid.uuid4(), "candidate_code": f"P{tag[:3]}{i:08d}", "name": f"Perf {i}", "email": f"p{tag}{i}@example.com",
             "source_id": source, "created_by_user_id": actor.id, "experience_months": i % 120, "notice_days": i % 90,
             "location": ("Hyderabad", "Pune", "Chennai")[i % 3], "preferred_locations": []}
            for i in range(10_000)
        ]
        await db_session.execute(insert(Candidate), people)
        held = [
            {"id": uuid.uuid4(), "candidate_id": p["id"], "skill_id": skills[(n + k) % 6].id, "level": "advanced", "added_by_user_id": actor.id}
            for n, p in enumerate(people) for k in range(3)
        ]
        await db_session.execute(insert(CandidateSkill), held)
        body = CandidateSearch(all=[skills[0].name, skills[1].name], any=[[skills[2].name, skills[5].name]], location="hyd")
        await candidate_search.search(db_session, body, limit=50, offset=0)  # warm: the rows were just written
        started = time.perf_counter()
        result = await candidate_search.search(db_session, body, limit=50, offset=0)
        elapsed = time.perf_counter() - started
        assert result["total"] > 0 and len(result["items"]) == 50
        assert elapsed < 2.0, f"search took {elapsed:.2f}s"
    finally:
        await db_session.rollback()
