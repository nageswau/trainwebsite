"""hrc-027 (DEC-SCOPE-398, spec docs/superpowers/specs/2026-11-05-hrc-027-candidate-job-recommendations-design.md): an IT student or an
external candidate reads the open jobs they may see in three views (J3-J5) with an explanation and the disclaimer (AC1-AC4), and applies
through one gate (J7/J8). The shared test database is never truncated, so every test searches its own tag (`q`) for exact sets."""

from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from app.models import Candidate, CandidateSkill, JobSkill, Notification
from app.services import matching
from tests.rec001_helpers import login, make_user
from tests.test_rec_016_matching import _world

pytestmark = pytest.mark.asyncio
JOBS = "/api/v1/candidate/jobs"
LEGACY_APPLY = "/api/v1/workflows/it/jobs/{}/apply"


async def _setup(client, db, role="it_student"):
    """A world with two skills, a job needing both, a job needing a skill nobody holds, and a signed-in caller holding both skills."""
    w = await _world(client, db)
    java, sql, rust = await w.skill("Java"), await w.skill("SQL"), await w.skill("Rust")
    match = await w.requirement(required=[(java, 2), (sql, 1)], work_mode="remote")
    other = await w.requirement(required=[(rust, 1)], work_mode="onsite")
    user = await make_user(db, role, "it")
    candidate = await w.candidate(java, sql, user_id=user.id, opted_in=True, preferred_role="Java Developer")
    await login(client, user)
    return w, user, candidate, match, other, (java, sql, rust)


async def _list(client, tag, **params):
    response = await client.get(JOBS, params={"q": tag, **params})
    assert response.status_code == 200, response.text
    return response.json()


def _ids(body) -> list[str]:
    return [item["id"] for item in body["items"]]


# --- the pure rule (J7) ------------------------------------------------------------------------------------------------------------
async def test_hard_filter_gaps_name_each_unmet_switched_on_filter(client, db_session):
    w = await _world(client, db_session)
    java = await w.skill("Java")
    job = await w.requirement(required=[(java, 1)], experience_min_months=24, match_hard_experience=True, work_mode="remote")
    candidate = await w.candidate(java)
    spec = await matching.spec(db_session, job)
    facts = (await matching.facts(db_session, [candidate], spec))[candidate.id]
    assert matching.hard_filter_gaps(spec, facts) == ["experience"]  # unknown experience fails (E6)
    facts["experience_months"] = 36
    assert matching.hard_filter_gaps(spec, facts) == []
    assert matching.skill_hits(spec, facts) == {spec.skills[0]["id"]: True}


# --- the three views (AC1-AC4) -----------------------------------------------------------------------------------------------------
async def test_a_matching_job_is_recommended_and_every_open_job_is_listed(client, db_session):
    w, _user, _c, match, other, _ = await _setup(client, db_session)
    recommended = await _list(client, w.tag, view="recommended")
    assert _ids(recommended) == [str(match.id)]  # AC1
    card = recommended["items"][0]
    assert card["recommended"] is True and card["matches_skills"] is True and card["match"]["score"] >= matching_threshold(recommended)
    assert card["match"]["explanation"][0]["text"] == "Matches 2 of 2 required skills"  # AC3
    assert recommended["disclaimer"] == matching.DISCLAIMER  # AC4
    assert recommended["counts"] == {"recommended": 1, "matching": 1, "all": 2} and recommended["reason"] is None
    everything = await _list(client, w.tag, view="all")
    assert set(_ids(everything)) == {str(match.id), str(other.id)}  # AC2
    rust_card = next(i for i in everything["items"] if i["id"] == str(other.id))
    assert rust_card["match"] is None and rust_card["matches_skills"] is False
    assert rust_card["skills_text"].startswith("Matches 0 of 1 required skills (missing Rust")  # AC3 on a non-match
    assert rust_card["work_mode"] == "onsite" and rust_card["required_skills"] == [f"Rust {w.tag}"]


def matching_threshold(body) -> int:
    return body["threshold"]


async def test_matching_view_holds_a_job_with_one_of_its_required_skills(client, db_session):
    w, _u, _c, match, _o, (java, _sql, rust) = await _setup(client, db_session)
    partial = await w.requirement(required=[(java, 1), (rust, 1)], work_mode="remote")
    body = await _list(client, w.tag, view="matching")
    assert _ids(body) == [str(match.id), str(partial.id)]  # the scored one first
    card = body["items"][1]
    assert card["match"] is None and card["recommended"] is False and "missing Rust" in card["skills_text"]


async def test_no_salary_reaches_a_card(client, db_session):
    w, _u, _c, _m, _o, (java, sql, _r) = await _setup(client, db_session)
    await w.requirement(required=[(java, 1)], salary_min=500000, salary_max=900000, work_mode="remote")
    body = await _list(client, w.tag, view="all")
    text = str(body)
    assert all("salary" not in key for item in body["items"] for key in item) and "900000" not in text and "Salary" not in text


async def test_a_profile_without_skills_gets_an_empty_recommended_view_and_the_prompt(client, db_session):
    w = await _world(client, db_session)
    java = await w.skill("Java")
    job = await w.requirement(required=[(java, 1)], work_mode="remote")
    student = await make_user(db_session, "it_student", "it")
    await login(client, student)
    before = await db_session.scalar(select(func.count()).select_from(Candidate))
    body = await _list(client, w.tag, view="recommended")
    assert body["items"] == [] and body["reason"] == "no_skills" and body["counts"]["all"] == 1
    assert _ids(await _list(client, w.tag, view="all")) == [str(job.id)]
    assert await db_session.scalar(select(func.count()).select_from(Candidate)) == before  # J9: reading creates nothing


async def test_internal_closed_and_other_segment_jobs_never_appear(client, db_session):
    w, _u, _c, match, _o, (java, _s, _r) = await _setup(client, db_session)
    hidden = [
        await w.requirement(required=[(java, 1)], visibility="internal"),
        await w.requirement(required=[(java, 1)], closes_on=date.today() - timedelta(days=1)),
        await w.requirement(required=[(java, 1)], status="on_hold"),
    ]
    body = await _list(client, w.tag, view="all")
    assert not {str(j.id) for j in hidden} & set(_ids(body)) and str(match.id) in _ids(body)
    for job in hidden:
        assert (await client.post(f"{JOBS}/{job.id}/apply")).status_code == 404
        assert (await client.post(LEGACY_APPLY.format(job.id), json={})).status_code == 404


async def test_search_paging_and_a_bad_view(client, db_session):
    w, _u, _c, match, other, _ = await _setup(client, db_session)
    page = await _list(client, w.tag, view="all", limit=1, offset=1)
    assert page["total"] == 2 and len(page["items"]) == 1 and page["limit"] == 1 and page["offset"] == 1
    assert _ids(await _list(client, f"rust {w.tag}", view="all")) == [str(other.id)]  # a skill name is searched
    assert (await client.get(JOBS, params={"view": "best"})).status_code == 422
    assert (await client.get(JOBS, params={"q": "x" * 101})).status_code == 422
    assert (await client.get(JOBS, params={"limit": 0})).status_code == 422
    assert (await _list(client, "100%_" + w.tag))["items"] == []  # wildcards are literal


async def test_staff_cannot_read_candidate_jobs(client, db_session):
    w = await _world(client, db_session)  # signed in as the recruiter
    assert (await client.get(JOBS)).status_code == 403
    assert (await client.post(f"{JOBS}/{w.recruiter.id}/apply")).status_code == 403


async def test_an_external_candidate_reads_and_applies(client, db_session):
    w, user, candidate, match, _o, _ = await _setup(client, db_session, role="candidate")
    assert _ids(await _list(client, w.tag, view="recommended")) == [str(match.id)]
    applied = await client.post(f"{JOBS}/{match.id}/apply")
    assert applied.status_code == 201, applied.text
    out = applied.json()
    assert out["code"].startswith("JA-") and out["status_label"] == "Received"
    notice = await db_session.scalar(select(Notification).where(Notification.user_id == user.id, Notification.title == "Application received"))
    assert notice.action_url == "/it/careers/portal/jobs"  # J10
    card = (await _list(client, w.tag, view="recommended"))["items"][0]
    assert card["application"] == {"code": out["code"], "status_label": "Received"} and card["can_apply"] is False
    assert (await client.post(f"{JOBS}/{match.id}/apply")).status_code == 409


async def test_a_student_applies_and_their_candidate_record_is_used(client, db_session):
    w, user, candidate, match, _o, _ = await _setup(client, db_session)
    applied = await client.post(f"{JOBS}/{match.id}/apply")
    assert applied.status_code == 201, applied.text
    again = await client.post(LEGACY_APPLY.format(match.id), json={})
    assert again.status_code == 409


async def test_a_hard_filter_blocks_applying_on_both_routes_and_the_card_says_why(client, db_session):
    w, _u, candidate, _m, _o, (java, _s, _r) = await _setup(client, db_session)
    job = await w.requirement(required=[(java, 1)], experience_min_months=24, match_hard_experience=True, work_mode="remote")
    card = next(i for i in (await _list(client, w.tag, view="all"))["items"] if i["id"] == str(job.id))
    assert card["can_apply"] is False and card["blocked"] == ["at least 2 yrs of experience"]
    for url in (f"{JOBS}/{job.id}/apply", LEGACY_APPLY.format(job.id)):
        refused = await client.post(url, json={})
        assert refused.status_code == 422 and "at least 2 yrs of experience" in refused.text
    candidate.experience_months = 30
    await db_session.commit()
    assert (await client.post(f"{JOBS}/{job.id}/apply")).status_code == 201


async def test_a_salary_hard_filter_is_explained_without_amounts(client, db_session):
    w, _u, _c, _m, _o, (java, _s, _r) = await _setup(client, db_session)
    job = await w.requirement(required=[(java, 1)], salary_max=600000, match_hard_salary=True, work_mode="remote")
    card = next(i for i in (await _list(client, w.tag, view="all"))["items"] if i["id"] == str(job.id))
    assert card["blocked"] == ["an expected salary within the job's budget"] and "600" not in str(card)
    refused = await client.post(f"{JOBS}/{job.id}/apply")
    assert refused.status_code == 422 and "600" not in refused.text


async def test_required_skills_do_not_block_applying(client, db_session):
    w, _u, _c, _m, other, _ = await _setup(client, db_session)
    assert (await client.post(f"{JOBS}/{other.id}/apply")).status_code == 201  # J7: skills rank, they do not gate


async def test_a_lower_level_skill_does_not_count(client, db_session):
    w, _u, candidate, _m, _o, (java, _s, _r) = await _setup(client, db_session)
    expert = await w.requirement(required=[(java, 1)], work_mode="remote")
    row = await db_session.scalar(select(CandidateSkill).where(CandidateSkill.candidate_id == candidate.id, CandidateSkill.skill_id == java.id))
    row.level = "beginner"
    skill = await db_session.scalar(select(JobSkill).where(JobSkill.job_id == expert.id))
    skill.min_level = "expert"
    await db_session.commit()
    card = next(i for i in (await _list(client, w.tag, view="all"))["items"] if i["id"] == str(expert.id))
    assert card["matches_skills"] is False and card["match"] is None
