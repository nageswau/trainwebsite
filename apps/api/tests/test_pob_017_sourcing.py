"""pob-017 (DEC-SCOPE-429) -- a requirement's sourcing plan (S1-S4, S8) and its source funnel (S5-S7): the plan saves (AC1), the funnel by
source ties out (AC2), deadline breaches are flagged (AC3) and a candidate whose source changes after submission stays counted under the
source they were submitted with (the edge case, S6). Who may do what (S9) and the audit (S10). Names are unique per test (shared database)."""

from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models import AuditLog, Candidate, JobApplication, RecCandidateSource, SavedCandidateSearch
from app.services import applications
from app.services.bdm_appointments import db_now, today_ist
from tests.rec001_helpers import login, make_pm, make_recruiter, make_user
from tests.test_rec_007_requirements import BASE, _company, _tag

pytestmark = pytest.mark.asyncio

APPS = "/api/v1/recruiter/applications"


@pytest_asyncio.fixture
async def db(db_session):
    return db_session


async def _source(db, name: str) -> RecCandidateSource:
    return await db.scalar(select(RecCandidateSource).where(func.lower(RecCandidateSource.name) == name.lower()))


async def _world(client, db) -> dict:
    manager = await make_pm(db)
    recruiter = await make_recruiter(db, manager, name=f"Src {_tag()}")
    outsider = await make_recruiter(db, await make_pm(db), name=f"Out {_tag()}")
    company = await _company(db, recruiter)
    await login(client, recruiter)
    response = await client.post(BASE, json={"company_id": str(company.id), "title": f"Sourced {_tag()}", "location": "Pune", "required_skills": ["Java"], "preferred_skills": ["Kafka"]})
    assert response.status_code == 201, response.text
    req = response.json()["requirement"]
    assert (await client.post(f"{BASE}/{req['id']}/status", json={"status": "requirement_received"})).status_code == 200
    return {"manager": manager, "recruiter": recruiter, "outsider": outsider, "company": company, "id": req["id"], "url": f"{BASE}/{req['id']}/sourcing"}


async def _candidate(db, creator, source: str) -> Candidate:
    candidate = Candidate(candidate_code=await applications.candidates.next_code(db), name=f"Cand {_tag()}", email=f"{_tag()}@example.com", preferred_locations=[],
                          source_id=(await _source(db, source)).id, created_by_user_id=creator.id)  # fmt: skip
    db.add(candidate)
    await db.commit()
    return candidate


async def _apply(client, db, w, source: str, *path: str) -> tuple[Candidate, str]:
    """A candidate from `source` added to the requirement, then moved through `path`."""
    candidate = await _candidate(db, w["recruiter"], source)
    response = await client.post(f"{BASE}/{w['id']}/candidates", json={"candidate_id": str(candidate.id)})
    assert response.status_code in (200, 201), response.text
    application_id = await db.scalar(select(JobApplication.id).where(JobApplication.candidate_id == candidate.id))
    for status in path:
        reason = {"rejection_reason": "skills_mismatch"} if status == "rejected" else {}
        moved = await client.post(f"{APPS}/{application_id}/status", json={"status": status, **reason})
        assert moved.status_code == 200, moved.text
    return candidate, str(application_id)


def _plan_body(w, **extra) -> dict:
    return {"target_profile": None, "boolean_strings": [], "channel_ids": [], "saved_search_ids": [], "target_found": None, "target_screened": None,
            "target_submitted": None, "deadline": None, "source_owner_user_id": None, **extra}  # fmt: skip


async def _put(client, w, expected: int = 200, **extra) -> dict:
    response = await client.put(w["url"], json=_plan_body(w, **extra))
    assert response.status_code == expected, response.text
    return response.json()


def _row(body: dict, name: str) -> dict:
    return next(r for r in body["funnel"]["rows"] if r["source"]["name"].lower() == name.lower())


# --- S1-S4, AC1: the plan -------------------------------------------------------------------------------------------------------------
async def test_a_new_requirement_has_an_empty_plan(client, db):
    w = await _world(client, db)
    response = await client.get(w["url"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["plan"]["target_profile"] is None and body["plan"]["boolean_strings"] == [] and body["plan"]["updated_at"] is None
    assert body["channels"] == [] and body["searches"] == [] and body["hidden_searches"] == 0
    assert body["funnel"]["total"] == {"found": 0, "screened": 0, "suitable": 0, "submitted": 0, "rejected": 0, "conversion": None}
    assert body["progress"]["state"] == "no_targets" and body["can_edit"] is True and body["can_link_searches"] is True


async def test_the_plan_saves_and_reads_back(client, db):
    w = await _world(client, db)
    linkedin, referral = await _source(db, "LinkedIn"), await _source(db, "Referral")
    deadline = (today_ist(await db_now(db)) + timedelta(days=10)).isoformat()
    strings = [{"label": "Naukri", "query": '("java developer" OR "backend engineer") AND kafka'}]
    body = await _put(client, w, target_profile="3-5 years Java backend, Pune", boolean_strings=strings, channel_ids=[str(linkedin.id), str(referral.id)],
                      target_found=40, target_screened=15, target_submitted=5, deadline=deadline, source_owner_user_id=str(w["recruiter"].id))  # fmt: skip
    again = (await client.get(w["url"])).json()
    assert again["plan"] == body["plan"]
    plan = again["plan"]
    assert plan["target_profile"] == "3-5 years Java backend, Pune" and plan["boolean_strings"] == strings
    assert (plan["target_found"], plan["target_screened"], plan["target_submitted"], plan["deadline"]) == (40, 15, 5, deadline)
    assert plan["source_owner"]["id"] == str(w["recruiter"].id) and plan["updated_by"]["id"] == str(w["recruiter"].id)
    assert {c["name"] for c in again["channels"]} == {linkedin.name, referral.name}
    assert {r["source"]["name"] for r in again["funnel"]["rows"]} == {linkedin.name, referral.name}  # planned channels listed with nothing found
    assert all(r["planned"] for r in again["funnel"]["rows"])
    audits = (await db.scalars(select(AuditLog).where(AuditLog.entity_id == w["id"], AuditLog.action == "requirement_sourcing_plan.update"))).all()
    assert len(audits) == 1 and "target_profile" in audits[0].metadata_json["fields"] and "3-5 years" not in str(audits[0].metadata_json)
    # the same plan again changes nothing and audits nothing
    await _put(client, w, target_profile="3-5 years Java backend, Pune", boolean_strings=strings, channel_ids=[str(referral.id), str(linkedin.id)],
               target_found=40, target_screened=15, target_submitted=5, deadline=deadline, source_owner_user_id=str(w["recruiter"].id))  # fmt: skip
    assert len((await db.scalars(select(AuditLog).where(AuditLog.entity_id == w["id"], AuditLog.action == "requirement_sourcing_plan.update"))).all()) == 1


@pytest.mark.parametrize(
    "extra",
    [
        {"target_found": -1},
        {"target_found": 10001},
        {"boolean_strings": [{"label": "x", "query": ""}]},
        {"boolean_strings": [{"label": "x", "query": "a"}] * 11},
        {"target_profile": "x" * 2001},
        {"unknown": 1},
    ],
)
async def test_invalid_plans_are_refused(client, db, extra):
    w = await _world(client, db)
    await _put(client, w, 422, **extra)


async def test_the_owner_must_be_on_the_requirement_and_channels_must_exist(client, db):
    w = await _world(client, db)
    refused = await _put(client, w, 422, source_owner_user_id=str(w["outsider"].id))
    assert "owner" in str(refused["detail"]).lower()
    await _put(client, w, 422, channel_ids=[w["id"]])  # not a source
    inactive = RecCandidateSource(name=f"Old fair {_tag()}", active=False)
    db.add(inactive)
    await db.commit()
    await _put(client, w, 422, channel_ids=[str(inactive.id)])


async def test_saved_searches_link_and_hidden_links_survive_a_save(client, db):
    w = await _world(client, db)
    mine = SavedCandidateSearch(owner_user_id=w["recruiter"].id, name=f"Java Pune {_tag()}", filters={"all": ["Java"]})
    other = SavedCandidateSearch(owner_user_id=w["outsider"].id, name=f"Private {_tag()}", filters={"all": ["Go"]})
    db.add_all([mine, other])
    await db.commit()
    await _put(client, w, 422, saved_search_ids=[str(other.id)])  # someone else's private search is not visible
    body = await _put(client, w, saved_search_ids=[str(mine.id)])
    assert [s["id"] for s in body["searches"]] == [str(mine.id)] and body["searches"][0]["filters"] == {"all": ["Java"]}
    # the super admin links their own private search; the recruiter cannot see it, and their save keeps it
    admin = await make_user(db, "super_admin", "global")
    secret = SavedCandidateSearch(owner_user_id=admin.id, name=f"Admin {_tag()}", filters={"all": ["Rust"]})
    db.add(secret)
    await db.commit()
    await login(client, admin)
    await _put(client, w, saved_search_ids=[str(mine.id), str(secret.id)])
    await login(client, w["recruiter"])
    seen = (await client.get(w["url"])).json()
    assert [s["id"] for s in seen["searches"]] == [str(mine.id)] and seen["hidden_searches"] == 1
    kept = await _put(client, w, saved_search_ids=[], target_found=3)
    assert kept["searches"] == [] and kept["hidden_searches"] == 1


# --- S5, S6, AC2 and the edge case: the funnel --------------------------------------------------------------------------------------
async def test_the_funnel_by_source_ties_out(client, db):
    w = await _world(client, db)
    await _apply(client, db, w, "Referral")  # found
    await _apply(client, db, w, "Referral", "screened")  # screened
    await _apply(client, db, w, "LinkedIn", "shortlisted")  # suitable (screened implied)
    await _apply(client, db, w, "LinkedIn", "screened", "profile_shared")  # submitted
    await _apply(client, db, w, "Referral", "shortlisted", "rejected")  # suitable, then rejected
    await _apply(client, db, w, "LinkedIn", "withdrawn")  # found only
    body = (await client.get(w["url"])).json()
    referral, linkedin = _row(body, "Referral"), _row(body, "LinkedIn")
    assert {k: referral[k] for k in ("found", "screened", "suitable", "submitted", "rejected")} == {"found": 3, "screened": 2, "suitable": 1, "submitted": 0, "rejected": 1}
    assert {k: linkedin[k] for k in ("found", "screened", "suitable", "submitted", "rejected")} == {"found": 3, "screened": 2, "suitable": 2, "submitted": 1, "rejected": 0}
    total = body["funnel"]["total"]
    for stage in ("found", "screened", "suitable", "submitted", "rejected"):
        assert total[stage] == sum(r[stage] for r in body["funnel"]["rows"])
    assert total["found"] == await db.scalar(select(func.count()).select_from(JobApplication).where(JobApplication.job_id == w["id"]))
    assert linkedin["conversion"] == pytest.approx(1 / 3) and referral["conversion"] == 0 and not linkedin["planned"]


async def test_a_source_change_after_submission_keeps_the_submitted_source(client, db):
    w = await _world(client, db)
    submitted, application_id = await _apply(client, db, w, "LinkedIn", "profile_shared")
    waiting, _ = await _apply(client, db, w, "LinkedIn")
    referral = await _source(db, "Referral")
    for candidate in (submitted, waiting):
        candidate.source_id = referral.id
    await db.commit()
    assert (await client.post(f"{APPS}/{application_id}/status", json={"status": "interview"})).status_code == 200  # a later move keeps it too
    body = (await client.get(w["url"])).json()
    assert (_row(body, "LinkedIn")["found"], _row(body, "LinkedIn")["submitted"]) == (1, 1)
    assert (_row(body, "Referral")["found"], _row(body, "Referral")["submitted"]) == (1, 0)  # not yet submitted: follows the candidate


async def test_the_snapshot_is_set_when_created_already_submitted(db):
    recruiter = await make_recruiter(db, await make_pm(db))
    company = await _company(db, recruiter)
    from app.models import Job

    job = Job(company_id=company.id, title=f"Direct {_tag()}", location="Pune", description="", skills=[], status="sourcing")
    db.add(job)
    await db.flush()
    candidate = await _candidate(db, recruiter, "LinkedIn")
    application = await applications.create(db, recruiter, job, candidate, "profile_shared", "Profile shared (Email)")
    await db.commit()
    assert application.submitted_source_id == candidate.source_id
    plain = await applications.create(db, recruiter, job, await _candidate(db, recruiter, "Referral"), "sourced")
    await db.commit()
    assert plain.submitted_source_id is None


# --- S7, AC3: progress and deadline breaches ----------------------------------------------------------------------------------------
async def test_a_passed_deadline_with_short_targets_is_breached(client, db):
    w = await _world(client, db)
    await _apply(client, db, w, "Referral", "screened")
    yesterday = (today_ist(await db_now(db)) - timedelta(days=1)).isoformat()
    body = await _put(client, w, target_found=5, target_screened=1, deadline=yesterday)
    progress = body["progress"]
    assert progress["state"] == "breached" and progress["short"] == ["found"]
    assert progress["found"] == {"actual": 1, "target": 5} and progress["screened"] == {"actual": 1, "target": 1}
    met = await _put(client, w, target_found=1, target_screened=1, deadline=yesterday)
    assert met["progress"]["state"] == "met" and met["progress"]["short"] == []
    ahead = await _put(client, w, target_found=5, deadline=(today_ist(await db_now(db)) + timedelta(days=3)).isoformat())
    assert ahead["progress"]["state"] == "on_track" and ahead["progress"]["days_left"] == 3
    open_ended = await _put(client, w, target_found=5)
    assert open_ended["progress"]["state"] == "on_track" and open_ended["progress"]["days_left"] is None


# --- S9: who may do what ----------------------------------------------------------------------------------------------------------
async def test_scope_role_and_cancelled_rules(client, db):
    w = await _world(client, db)
    await login(client, w["outsider"])
    assert (await client.get(w["url"])).status_code == 404
    assert (await client.put(w["url"], json=_plan_body(w))).status_code == 404
    await login(client, w["manager"])  # a Team Lead reads but is not a requirement writer (WRITERS)
    read = await client.get(w["url"])
    assert read.status_code == 200 and read.json()["can_edit"] is False
    assert (await client.put(w["url"], json=_plan_body(w))).status_code == 403
    await login(client, w["recruiter"])
    assert (await client.post(f"{BASE}/{w['id']}/status", json={"status": "cancelled", "note": "Client paused"})).status_code == 200
    assert (await client.get(w["url"])).json()["can_edit"] is False
    assert (await client.put(w["url"], json=_plan_body(w))).status_code == 409
