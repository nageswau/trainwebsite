"""hrc-019 -- advanced multi-filter resume search (DEC-SCOPE-399; design
docs/superpowers/specs/2026-11-05-hrc-019-advanced-candidate-search-design.md, rules S1-S14). Every test makes its own skills (unique
names), so only its own candidates can ever match; the shared database is never truncated."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import event, select, text, update

from app.core.database import engine
from app.models import (
    Candidate,
    CandidateDocument,
    CandidateEducation,
    CandidateEmployment,
    CandidateResume,
    Interview,
    JobApplication,
    SkillCategory,
    SkillCategoryTag,
)
from app.schemas import CandidateSearch
from app.services import candidate_search
from tests.rec001_helpers import login, make_user
from tests.test_rec_013_find_candidates import SEARCH, _ids, _search, _world
from tests.test_rec_017_tracking import _requirement

pytestmark = pytest.mark.asyncio


async def _education(w, candidate, **row):
    w.db.add(CandidateEducation(candidate_id=candidate.id, position=row.pop("position", 1), **row))
    await w.db.commit()


async def _job(w, candidate, start=date(2020, 1, 1), end=None, **row):
    w.db.add(CandidateEmployment(candidate_id=candidate.id, position=row.pop("position", 1), employer=row.pop("employer", "Acme"),
                                 start_date=start, end_date=end, **row))
    await w.db.commit()


# --- S3 skills ---------------------------------------------------------------------------------------------------------------------
async def test_category_filter_matches_a_primary_or_a_secondary_category(client, db_session):
    w = await _world(client, db_session)
    cat = SkillCategory(name=f"Cat {w.tag}")
    db_session.add(cat)
    await db_session.flush()
    java, tagged = await w.skill("Java"), await w.skill("Tagged")
    db_session.add(SkillCategoryTag(skill_id=tagged.id, category_id=cat.id))
    primary = await w.skill("Primary")
    primary.category_id = cat.id
    await db_session.commit()
    a = await w.candidate(java, primary)
    b = await w.candidate(java, tagged)
    await w.candidate(java)
    assert _ids(await _search(client, all=[java.name], category_ids=[str(cat.id)])) == {str(a.id), str(b.id)}
    # a category alone is a search
    assert _ids(await _search(client, category_ids=[str(cat.id)])) == {str(a.id), str(b.id)}


async def test_min_level_and_per_skill_months_apply_to_every_term(client, db_session):
    w = await _world(client, db_session)
    java = await w.skill("Java")
    a = await w.candidate(java)  # level advanced
    await db_session.execute(text("UPDATE candidate_skills SET experience_months = 30 WHERE candidate_id = :c"), {"c": a.id})
    b = await w.candidate(java)
    await db_session.execute(text("UPDATE candidate_skills SET level = 'beginner', experience_months = 40 WHERE candidate_id = :c"), {"c": b.id})
    await db_session.commit()
    assert _ids(await _search(client, all=[java.name], min_level="intermediate")) == {str(a.id)}
    assert _ids(await _search(client, all=[java.name], skill_min_months=36)) == {str(b.id)}
    assert _ids(await _search(client, all=[java.name], skill_min_months=24)) == {str(a.id), str(b.id)}


async def test_preferred_skills_never_filter_but_rank_and_explain(client, db_session):
    w = await _world(client, db_session)
    java, docker = await w.skill("Java"), await w.skill("Docker")
    plain = await w.candidate(java)
    both = await w.candidate(java, docker)
    response = await _search(client, all=[java.name], preferred=[docker.name], sort="match")
    assert [i["id"] for i in response.json()["items"]] == [str(both.id), str(plain.id)]
    cards = {i["id"]: i["match"] for i in response.json()["items"]}
    assert cards[str(plain.id)] == {"required": [{"term": java.name, "skill": java.name, "held": True}],
                                    "preferred": [{"term": docker.name, "skill": docker.name, "held": False}]}
    assert cards[str(both.id)]["preferred"][0]["held"] is True
    # preferred alone is a search: it lists everyone who holds one, best first
    assert _ids(await _search(client, preferred=[docker.name])) == {str(both.id)}


async def test_any_group_terms_show_which_one_was_held(client, db_session):
    w = await _world(client, db_session)
    aws, azure = await w.skill("AWS"), await w.skill("Azure")
    c = await w.candidate(aws)
    item = (await _search(client, any=[[aws.name, azure.name]])).json()["items"][0]
    assert item["id"] == str(c.id)
    assert item["match"]["required"] == [{"term": aws.name, "skill": aws.name, "held": True}, {"term": azure.name, "skill": azure.name, "held": False}]


# --- S4 education (same row) -------------------------------------------------------------------------------------------------------
async def test_education_filters_need_one_row_to_satisfy_them_all(client, db_session):
    w = await _world(client, db_session)
    java = await w.skill("Java")
    good = await w.candidate(java)
    await _education(w, good, degree="B.Tech", specialisation="Computer Science", institution="JNTU Hyderabad", year=2020, grade="8.2")
    split = await w.candidate(java)  # the degree on one row, the institution on another: not the same row
    await _education(w, split, degree="B.Tech", institution="Other College", year=2020)
    await _education(w, split, position=2, degree="MBA", institution="JNTU Hyderabad", year=2022)
    pct = await w.candidate(java)
    await _education(w, pct, degree="B.Tech", institution="JNTU Kakinada", year=2019, grade="82%")
    assert _ids(await _search(client, all=[java.name], degree="b.tech", institution="jntu")) == {str(good.id), str(pct.id)}
    assert _ids(await _search(client, all=[java.name], degree="B.Tech", institution="Hyderabad")) == {str(good.id)}
    assert _ids(await _search(client, all=[java.name], specialisation="computer")) == {str(good.id)}
    assert _ids(await _search(client, all=[java.name], passing_year_min=2020, passing_year_max=2021)) == {str(good.id), str(split.id)}
    # CGPA compares only a plain 0-10 number ("82%" never matches)
    assert _ids(await _search(client, all=[java.name], cgpa_min=8, cgpa_max=10)) == {str(good.id)}
    assert _ids(await _search(client, all=[java.name], cgpa_min=0)) == {str(good.id)}


# --- S5 experience -----------------------------------------------------------------------------------------------------------------
async def test_fresher_relevant_and_employment_filters(client, db_session):
    w = await _world(client, db_session)
    java = await w.skill("Java")
    fresher = await w.candidate(java, experience_months=0)
    unknown = await w.candidate(java)  # experience not recorded is not a fresher
    senior = await w.candidate(java, experience_months=60, relevant_experience_months=36)
    await _job(w, senior, designation="Senior Java Developer", industry="Banking", employment_type="full_time")
    contractor = await w.candidate(java, experience_months=24, relevant_experience_months=12)
    await _job(w, contractor, designation="Developer", industry="Banking", employment_type="contract")
    assert _ids(await _search(client, all=[java.name], fresher=True)) == {str(fresher.id)}
    assert str(unknown.id) not in _ids(await _search(client, all=[java.name], fresher=True))
    assert _ids(await _search(client, all=[java.name], relevant_min_months=24, relevant_max_months=59)) == {str(senior.id)}
    assert _ids(await _search(client, all=[java.name], designation="java dev")) == {str(senior.id)}
    assert _ids(await _search(client, all=[java.name], industry="bank")) == {str(senior.id), str(contractor.id)}
    assert _ids(await _search(client, all=[java.name], employment_types=["contract"])) == {str(contractor.id)}
    # same row: Senior designation with a contract row does not exist
    assert _ids(await _search(client, all=[java.name], designation="senior", employment_types=["contract"])) == set()


# --- S6 / S7 location and preferences ----------------------------------------------------------------------------------------------
async def test_location_and_preference_filters(client, db_session):
    w = await _world(client, db_session)
    java = await w.skill("Java")
    a = await w.candidate(java, country="India", state="Telangana", city="Hyderabad", preferred_locations=["Bengaluru", "Pune"],
                          willing_to_relocate=True, work_modes=["remote", "hybrid"], preferred_role="Backend Developer",
                          preferred_roles=["Java Developer"], employment_types=["full_time"])
    b = await w.candidate(java, country="India", state="Maharashtra", city="Pune", preferred_locations=["Mumbai"], willing_to_relocate=False,
                          work_modes=["onsite"], preferred_roles=["Tester"], employment_types=["contract"])
    assert _ids(await _search(client, all=[java.name], country="india")) == {str(a.id), str(b.id)}
    assert _ids(await _search(client, all=[java.name], state="telan")) == {str(a.id)}
    assert _ids(await _search(client, all=[java.name], city="pune")) == {str(b.id)}
    assert _ids(await _search(client, all=[java.name], preferred_location="bengal")) == {str(a.id)}
    assert _ids(await _search(client, all=[java.name], willing_to_relocate=True)) == {str(a.id)}
    assert _ids(await _search(client, all=[java.name], work_modes=["onsite", "remote"])) == {str(a.id), str(b.id)}
    assert _ids(await _search(client, all=[java.name], work_modes=["hybrid"])) == {str(a.id)}
    assert _ids(await _search(client, all=[java.name], preferred_role="java dev")) == {str(a.id)}
    assert _ids(await _search(client, all=[java.name], preferred_role="backend")) == {str(a.id)}
    assert _ids(await _search(client, all=[java.name], preferred_employment_types=["contract"])) == {str(b.id)}


# --- S8 recruitment data, documents, applications ----------------------------------------------------------------------------------
async def test_owner_registration_documents_and_applications(client, db_session):
    w = await _world(client, db_session)
    java = await w.skill("Java")
    mine = await w.candidate(java, owner_user_id=w.actor.id)
    loose = await w.candidate(java)
    await db_session.execute(update(Candidate).where(Candidate.id == loose.id).values(created_at=datetime(2024, 3, 10, 20, 0, tzinfo=UTC)))
    db_session.add(CandidateResume(candidate_id=mine.id, version=1, storage_key=f"k/{uuid.uuid4()}", content_type="application/pdf",
                                   size_bytes=10, uploaded_by_user_id=w.actor.id, extracted_text="java"))
    db_session.add(CandidateDocument(candidate_id=loose.id, document_type="payslip", storage_key=f"k/{uuid.uuid4()}", content_type="application/pdf",
                                     size_bytes=10, uploaded_by_user_id=w.actor.id))
    job = await _requirement(db_session)
    application = JobApplication(job_id=job.id, candidate_id=mine.id, status="interview")
    db_session.add(application)
    await db_session.flush()
    db_session.add(Interview(application_id=application.id, scheduled_at=datetime.now(UTC) + timedelta(days=1), mode="video"))
    await db_session.commit()
    assert _ids(await _search(client, all=[java.name], owner="me")) == {str(mine.id)}
    assert _ids(await _search(client, all=[java.name], owner="unassigned")) == {str(loose.id)}
    # 2024-03-10 20:00 UTC is 2024-03-11 01:30 in IST: registration dates are IST days
    assert _ids(await _search(client, all=[java.name], registered_from="2024-03-11", registered_to="2024-03-11")) == {str(loose.id)}
    assert _ids(await _search(client, all=[java.name], registered_to="2024-03-10")) == set()
    assert _ids(await _search(client, all=[java.name], has_resume=True)) == {str(mine.id)}
    assert _ids(await _search(client, all=[java.name], has_resume=False)) == {str(loose.id)}
    assert _ids(await _search(client, all=[java.name], document_types=["payslip", "id_proof"])) == {str(loose.id)}
    assert _ids(await _search(client, all=[java.name], application_statuses=["interview"])) == {str(mine.id)}
    assert _ids(await _search(client, all=[java.name], interviewed=True)) == {str(mine.id)}


# --- S9 package and the unknown option (AC4) ---------------------------------------------------------------------------------------
async def test_package_ranges_and_unknown_is_included_only_when_chosen(client, db_session):
    w = await _world(client, db_session)
    java = await w.skill("Java")
    within = await w.candidate(java, expected_salary=Decimal("800000"), current_annual_inr=Decimal("600000"), minimum_annual_inr=Decimal("700000"))
    above = await w.candidate(java, expected_salary=Decimal("1500000"), current_annual_inr=Decimal("1200000"))
    unknown = await w.candidate(java)
    body = {"all": [java.name], "salary_min": 600000, "salary_max": 1000000}
    assert _ids(await _search(client, **body)) == {str(within.id)}
    assert _ids(await _search(client, **body, package_unknown=True)) == {str(within.id), str(unknown.id)}
    assert _ids(await _search(client, all=[java.name], current_min=1000000)) == {str(above.id)}
    assert _ids(await _search(client, all=[java.name], current_max=700000, package_unknown=True)) == {str(within.id), str(unknown.id)}
    assert _ids(await _search(client, all=[java.name], minimum_min=500000, minimum_max=750000)) == {str(within.id)}
    # unknown alone, with no range, filters nothing
    assert _ids(await _search(client, all=[java.name], package_unknown=True)) == {str(within.id), str(above.id), str(unknown.id)}


@pytest.mark.parametrize("extra", [
    {"current_min": 1}, {"current_max": 1}, {"minimum_min": 1}, {"minimum_max": 1}, {"package_unknown": True}, {"sort": "package"},
])
async def test_package_filters_and_sort_are_403_without_the_grant(client, db_session, extra):
    w = await _world(client, db_session)
    java = await w.skill("Java")
    await w.candidate(java)
    assert (await _search(client, all=[java.name], **extra)).status_code == 200
    hr = await make_user(db_session, "hr_team", "it")
    await login(client, hr)
    response = await _search(client, all=[java.name], **extra)
    assert response.status_code == 403, response.text
    # the rest still works for that role
    assert (await _search(client, all=[java.name], sort="experience")).status_code == 200


# --- S10 sorting (AC3) -------------------------------------------------------------------------------------------------------------
async def _order(client, sort, java):
    response = await _search(client, all=[java.name], sort=sort)
    assert response.status_code == 200, response.text
    return [i["id"] for i in response.json()["items"]]


async def test_every_sort_key(client, db_session):
    w = await _world(client, db_session)
    java = await w.skill("Java")
    old = await w.candidate(java, experience_months=10, expected_salary=Decimal("900000"))
    mid = await w.candidate(java, experience_months=50, expected_salary=Decimal("500000"))
    new = await w.candidate(java)
    base = datetime.now(UTC)
    for n, c in enumerate((old, mid, new)):
        await db_session.execute(update(Candidate).where(Candidate.id == c.id).values(created_at=base - timedelta(days=30 - n), updated_at=base - timedelta(days=30 - n)))
    await db_session.execute(update(Candidate).where(Candidate.id == old.id).values(updated_at=base, email_verified_at=base, preferred_roles=["X"], preferred_locations=["Y"]))
    await db_session.commit()
    o, m, n = str(old.id), str(mid.id), str(new.id)
    assert await _order(client, "relevance", java) == [n, m, o]
    assert await _order(client, "registered", java) == [n, m, o]
    assert await _order(client, "experience", java) == [m, o, n]
    assert await _order(client, "package", java) == [m, o, n]
    assert await _order(client, "activity", java) == [o, n, m]
    assert await _order(client, "completeness", java) == [o, m, n]


async def test_completeness_sql_matches_the_profile_percent(client, db_session):
    """S10: the SQL expression gives the same percent as hrc-010's Python completeness, for an empty, a partial and a full profile."""
    from app.services import candidate_profile

    w = await _world(client, db_session)
    a, b, c = await w.skill("A"), await w.skill("B"), await w.skill("C")
    empty = await w.candidate()
    partial = await w.candidate(a, experience_months=0, preferred_roles=["Dev"], preferred_locations=[])
    full = await w.candidate(a, b, c, experience_months=30, expected_salary=Decimal("1"), preferred_roles=["Dev"], preferred_locations=["Pune"],
                             email_verified_at=datetime.now(UTC))
    await _education(w, full, degree="BSc")
    db_session.add(CandidateResume(candidate_id=full.id, version=1, storage_key=f"k/{uuid.uuid4()}", content_type="application/pdf", size_bytes=1,
                                   uploaded_by_user_id=w.actor.id))
    await db_session.commit()
    for cand, expected in ((empty, 0), (partial, 15), (full, 100)):
        await db_session.refresh(cand)
        stored = await candidate_profile.rows(db_session, cand.id)
        skills = await candidate_profile.skill_count(db_session, cand.id)
        resumes = int(cand is full)
        assert candidate_profile.completeness(cand, stored, skills, resumes)["percent"] == expected
        assert await db_session.scalar(select(candidate_search.completeness()).where(Candidate.id == cand.id)) == expected


# --- S13 validation ----------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("body, needle", [
    ({"sort": "salary"}, "sort"),
    ({"cgpa_min": 9, "cgpa_max": 7}, "CGPA"),
    ({"cgpa_max": 11}, "CGPA"),
    ({"passing_year_min": 2022, "passing_year_max": 2020}, "year"),
    ({"relevant_min_months": 40, "relevant_max_months": 10}, "relevant"),
    ({"current_min": 9, "current_max": 1}, "current"),
    ({"registered_from": "2024-03-11", "registered_to": "2024-03-01"}, "registration"),
    ({"registered_from": "11-03-2024"}, "Registered from"),
    ({"owner": "someone"}, "Owner"),
    ({"degree": "x" * 121}, "Degree"),
    ({"category_ids": [str(uuid.uuid4()) for _ in range(11)]}, "categories"),
    ({"work_modes": ["moon"]}, "Work mode"),
])
async def test_bad_bodies_are_422(client, db_session, body, needle):
    w = await _world(client, db_session)
    java = await w.skill("Java")
    response = await _search(client, all=[java.name], **body)
    assert response.status_code == 422, response.text
    assert needle.lower() in response.text.lower()


async def test_filters_alone_are_still_not_a_search(client, db_session):
    await _world(client, db_session)
    response = await _search(client, degree="B.Tech")
    assert response.status_code == 422 and "skill" in response.text


# --- AC1: the backlog example -----------------------------------------------------------------------------------------------------
async def test_java_and_spring_boot_relevant_2_to_5_years_6_to_10_lpa(client, db_session):
    """Backlog "+": Java AND Spring Boot; relevant 2-5 yrs; ₹6-10 LPA -- exactly the seeded matches."""
    w = await _world(client, db_session)
    java, spring = await w.skill("Java"), await w.skill("Spring Boot")
    hit = await w.candidate(java, spring, relevant_experience_months=36, expected_salary=Decimal("800000"))
    edge = await w.candidate(java, spring, relevant_experience_months=24, expected_salary=Decimal("1000000"))
    await w.candidate(java, spring, relevant_experience_months=72, expected_salary=Decimal("800000"))  # too senior
    await w.candidate(java, spring, relevant_experience_months=36, expected_salary=Decimal("1200000"))  # over budget
    await w.candidate(java, relevant_experience_months=36, expected_salary=Decimal("800000"))  # no Spring Boot
    body = {"all": [java.name, spring.name], "relevant_min_months": 24, "relevant_max_months": 71, "salary_min": 600000, "salary_max": 1000000}
    assert _ids(await _search(client, **body)) == {str(hit.id), str(edge.id)}


# --- edge cases -------------------------------------------------------------------------------------------------------------------
async def test_no_resume_and_a_text_query_is_simply_not_matched(client, db_session):
    w = await _world(client, db_session)
    java = await w.skill("Java")
    await w.candidate(java)
    response = await _search(client, all=[java.name], text=f"zebracode{w.tag}")
    assert response.status_code == 200 and response.json()["total"] == 0


# --- S12 performance --------------------------------------------------------------------------------------------------------------
async def test_query_count_is_unchanged_with_every_group_and_a_sort(client, db_session):
    w = await _world(client, db_session)
    java, docker = await w.skill("Java"), await w.skill("Docker")
    for _ in range(3):  # every candidate satisfies every filter below, so both searches read a page (and its skills)
        c = await w.candidate(java, docker, experience_months=12, country="India", work_modes=["remote"], owner_user_id=w.actor.id)
        await _education(w, c, degree="B.Tech")
        await _job(w, c, designation="Developer")
    statements: list[str] = []
    listener = lambda *args: statements.append(args[2])  # noqa: E731
    event.listen(engine.sync_engine, "before_cursor_execute", listener)
    try:
        statements.clear()
        assert (await _search(client, all=[java.name])).json()["total"] == 3
        plain = len([s for s in statements if s.lstrip().upper().startswith("SELECT")])
        statements.clear()
        full = {
            "all": [java.name], "preferred": [docker.name], "min_level": "beginner", "degree": "tech", "designation": "dev", "country": "ind",
            "work_modes": ["remote"], "owner": "me", "has_resume": False, "fresher": False, "interviewed": False, "package_unknown": True,
            "salary_min": 1, "current_max": 9, "registered_from": "2020-01-01", "sort": "activity",
        }
        assert (await _search(client, **full)).json()["total"] == 3
        assert len([s for s in statements if s.lstrip().upper().startswith("SELECT")]) == plain
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener)


@pytest.mark.parametrize("body", [
    {"all": ["Java", "Spring Boot"], "relevant_min_months": 24, "relevant_max_months": 71, "salary_min": 600000, "salary_max": 1000000},
    {"any": [["Python", "Java"]], "degree": "B.Tech", "institution": "JNTU", "city": "Hyderabad", "sort": "experience"},
    {"all": ["Java"], "designation": "Developer", "work_modes": ["remote"], "package_unknown": True, "salary_max": 900000, "sort": "activity"},
    {"text": "microservices", "fresher": True, "has_resume": True, "application_statuses": ["shortlisted"], "sort": "completeness"},
])
async def test_example_searches_plan_with_explain(db_session, body):
    """S12: the four example searches compile and plan (EXPLAIN) -- unknown example skills resolve to 'matches nobody' here."""
    search = CandidateSearch.model_validate(body)
    terms = await candidate_search.resolve_terms(db_session, search, strict=False)
    statement = candidate_search.page_statement(search, candidate_search.filters(search, terms, user_id=uuid.uuid4()), terms, 50, 0)
    compiled = statement.compile(dialect=engine.dialect, compile_kwargs={"render_postcompile": True})
    connection = await db_session.connection()
    plan = (await connection.exec_driver_sql(f"EXPLAIN {compiled}", tuple(compiled.params[name] for name in compiled.positiontup))).all()
    assert plan and "Limit" in plan[0][0]


async def test_ten_thousand_candidates_every_sort_within_budget(db_session):
    """S12 (Q-20 unconfirmed): on rec-013's 10k pool (rolled back), each new sort with a few filters stays inside rec-013's 2 s budget."""
    import time

    from sqlalchemy import insert

    from app.models import CandidateSkill, RecCandidateSource, Skill
    from tests.rec001_helpers import make_recruiter

    actor = await make_recruiter(db_session)
    category = await db_session.scalar(select(SkillCategory.id).where(SkillCategory.name == "Programming"))
    source = await db_session.scalar(select(RecCandidateSource.id).where(RecCandidateSource.name == "Referral"))
    tag = uuid.uuid4().hex[:8]
    skills = [Skill(id=uuid.uuid4(), name=f"Perf19 {i} {tag}", category_id=category) for i in range(4)]
    db_session.add_all(skills)
    await db_session.flush()
    try:
        people = [
            {"id": uuid.uuid4(), "candidate_code": f"Q{tag[:3]}{i:08d}", "name": f"Perf {i}", "email": f"q{tag}{i}@example.com", "source_id": source,
             "created_by_user_id": actor.id, "experience_months": i % 120, "relevant_experience_months": i % 60, "city": ("Hyderabad", "Pune")[i % 2],
             "preferred_locations": ["Pune"], "work_modes": ["remote"], "expected_annual_inr": 300000 + i * 100}
            for i in range(10_000)
        ]  # fmt: skip
        await db_session.execute(insert(Candidate), people)
        held = [{"id": uuid.uuid4(), "candidate_id": p["id"], "skill_id": skills[(n + k) % 4].id, "level": "advanced", "added_by_user_id": actor.id}
                for n, p in enumerate(people) for k in range(2)]  # fmt: skip
        await db_session.execute(insert(CandidateSkill), held)
        for sort in ("match", "experience", "package", "activity", "completeness"):
            body = CandidateSearch(any=[[skills[0].name, skills[1].name]], preferred=[skills[2].name], city="hyd", relevant_min_months=6,
                                   work_modes=["remote"], package_unknown=True, salary_max=2000000, sort=sort)  # fmt: skip
            await candidate_search.search(db_session, body, limit=50, offset=0, user_id=actor.id)
            started = time.perf_counter()
            result = await candidate_search.search(db_session, body, limit=50, offset=0, user_id=actor.id)
            elapsed = time.perf_counter() - started
            assert result["total"] > 0 and len(result["items"]) == 50
            assert elapsed < 2.0, f"{sort} took {elapsed:.2f}s"
    finally:
        await db_session.rollback()


# --- reuse: talent pools build bodies without validation ------------------------------------------------------------------------
async def test_a_constructed_rule_body_adds_no_filters(db_session):
    body = CandidateSearch.model_construct(all=[], any=[], experience_min_months=12, experience_max_months=None)
    assert len(candidate_search.filters(body, {})) == len(candidate_search.filters(CandidateSearch.model_construct(all=[], any=[]), {})) + 1


async def test_search_endpoint_path_is_unchanged():
    assert SEARCH == "/api/v1/recruiter/candidates/search"
