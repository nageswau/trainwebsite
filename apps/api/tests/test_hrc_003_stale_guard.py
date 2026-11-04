"""hrc-003 (DEC-SCOPE-370 S1-S6) -- concurrent-edit protection: a save carrying an older token than the stored record is a 409
`record_changed` with who/what/when and the current record; nothing is overwritten. No token = the old behaviour (S2)."""

import pytest
from sqlalchemy import select

from app.models import Candidate, Interview
from tests.rec001_helpers import login, make_recruiter, make_user
from tests.test_rec_017_tracking import _add, _candidate, _requirement, _tag, _team
from tests.test_rec_020_interviews import _interview

REQ = "/api/v1/recruiter/requirements"
CANDIDATES = "/api/v1/recruiter/candidates"
INTERVIEWS = "/api/v1/recruiter/interviews"


def _conflict(response, field: str, actor) -> dict:
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "record_changed"
    assert detail["message"] == "This record changed since you opened it"
    assert field in detail["changed_fields"]
    assert detail["changed_by"]["id"] == str(actor.id)
    assert detail["changed_at"]
    return detail["current"]


@pytest.mark.asyncio
async def test_a_stale_requirement_save_is_refused_with_the_changes_and_nothing_is_overwritten(client, db_session):
    _manager, recruiter = await _team(client, db_session)
    editor = await make_user(db_session, "super_admin", "global")
    job = await _requirement(db_session, recruiter)
    opened = (await client.get(f"{REQ}/{job.id}")).json()["requirement"]["updated_at"]

    await login(client, editor)
    first = await client.patch(f"{REQ}/{job.id}", json={"title": "Edited by the admin", "expected_updated_at": opened})
    assert first.status_code == 200, first.text

    await login(client, recruiter)
    stale = await client.patch(f"{REQ}/{job.id}", json={"title": "Edited by the recruiter", "location": "Chennai", "expected_updated_at": opened})
    current = _conflict(stale, "title", editor)
    assert current["title"] == "Edited by the admin" and current["location"] == "Pune"
    await db_session.refresh(job)
    assert (job.title, job.location) == ("Edited by the admin", "Pune")  # AC3: no silent overwrite

    retried = await client.patch(f"{REQ}/{job.id}", json={"title": "Edited by the recruiter", "expected_updated_at": current["updated_at"]})
    assert retried.status_code == 200, retried.text  # AC2: after reload the save succeeds
    assert retried.json()["requirement"]["title"] == "Edited by the recruiter"


@pytest.mark.asyncio
async def test_a_requirement_save_without_a_token_or_with_the_current_one_works_as_before(client, db_session):
    _manager, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    assert (await client.patch(f"{REQ}/{job.id}", json={"title": f"No token {_tag()}"})).status_code == 200
    token = (await client.get(f"{REQ}/{job.id}")).json()["requirement"]["updated_at"]
    assert (await client.patch(f"{REQ}/{job.id}", json={"title": f"Fresh {_tag()}", "expected_updated_at": token})).status_code == 200


@pytest.mark.asyncio
async def test_a_skills_only_change_moves_the_token(client, db_session):
    _manager, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    opened = (await client.get(f"{REQ}/{job.id}")).json()["requirement"]["updated_at"]
    saved = await client.patch(f"{REQ}/{job.id}", json={"required_skills": [f"Skill {_tag()}"], "expected_updated_at": opened})
    assert saved.status_code == 200, saved.text
    assert saved.json()["requirement"]["updated_at"] != opened
    stale = await client.patch(f"{REQ}/{job.id}", json={"title": f"Late {_tag()}", "expected_updated_at": opened})
    _conflict(stale, "skills", recruiter)


@pytest.mark.asyncio
async def test_scope_is_checked_before_the_token(client, db_session):
    _manager, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    opened = (await client.get(f"{REQ}/{job.id}")).json()["requirement"]["updated_at"]
    await client.patch(f"{REQ}/{job.id}", json={"title": f"Moved {_tag()}"})
    await login(client, await make_recruiter(db_session))  # another team: the requirement does not exist for them
    assert (await client.patch(f"{REQ}/{job.id}", json={"title": "x", "expected_updated_at": opened})).status_code == 404


@pytest.mark.asyncio
async def test_a_bad_token_is_a_422(client, db_session):
    _manager, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    assert (await client.patch(f"{REQ}/{job.id}", json={"title": "x", "expected_updated_at": "yesterday"})).status_code == 422


@pytest.mark.asyncio
async def test_a_stale_candidate_save_is_refused(client, db_session):
    _manager, recruiter = await _team(client, db_session)
    editor = await make_user(db_session, "super_admin", "global")
    candidate = await _candidate(db_session, recruiter)
    opened = (await client.get(f"{CANDIDATES}/{candidate.id}")).json()["updated_at"]

    await login(client, editor)
    first = await client.patch(f"{CANDIDATES}/{candidate.id}", json={"current_company": "Acme", "expected_updated_at": opened})
    assert first.status_code == 200, first.text

    await login(client, recruiter)
    stale = await client.patch(f"{CANDIDATES}/{candidate.id}", json={"current_company": "Globex", "expected_updated_at": opened})
    current = _conflict(stale, "current_company", editor)
    assert current["current_company"] == "Acme"
    assert (await db_session.scalar(select(Candidate.current_company).where(Candidate.id == candidate.id).execution_options(populate_existing=True))) == "Acme"
    retried = await client.patch(f"{CANDIDATES}/{candidate.id}", json={"current_company": "Globex", "expected_updated_at": current["updated_at"]})
    assert retried.status_code == 200, retried.text


@pytest.mark.asyncio
async def test_a_stale_interview_save_is_refused(client, db_session):
    _manager, recruiter = await _team(client, db_session)
    editor = await make_user(db_session, "super_admin", "global")
    job = await _requirement(db_session, recruiter)
    application = (await _add(client, job, await _candidate(db_session, recruiter))).json()["application"]
    interview = await _interview(client, application["id"])
    opened = interview["updated_at"]  # S6: the shape carries the token

    await login(client, editor)
    first = await client.patch(f"{INTERVIEWS}/{interview['id']}", json={"interviewer": "Priya", "expected_updated_at": opened})
    assert first.status_code == 200, first.text

    await login(client, recruiter)
    stale = await client.patch(f"{INTERVIEWS}/{interview['id']}", json={"interviewer": "Arun", "expected_updated_at": opened})
    current = _conflict(stale, "interviewer", editor)
    assert current["interviewer"] == "Priya"
    assert (await db_session.scalar(select(Interview.interviewer).where(Interview.id == interview["id"]).execution_options(populate_existing=True))) == "Priya"
    retried = await client.patch(f"{INTERVIEWS}/{interview['id']}", json={"interviewer": "Arun", "expected_updated_at": current["updated_at"]})
    assert retried.status_code == 200, retried.text


@pytest.mark.asyncio
async def test_a_stale_jd_save_is_refused(client, db_session):
    _manager, recruiter = await _team(client, db_session)
    editor = await make_user(db_session, "super_admin", "global")
    job = await _requirement(db_session, recruiter)

    await login(client, editor)
    first = await client.post(f"{REQ}/{job.id}/jd", json={"role": "Backend engineer", "expected_version": 0})
    assert first.status_code == 201, first.text

    await login(client, recruiter)
    stale = await client.post(f"{REQ}/{job.id}/jd", json={"role": "Frontend engineer", "expected_version": 0})
    current = _conflict(stale, "role", editor)
    assert current["versions"][0]["role"] == "Backend engineer"
    assert (await client.get(f"{REQ}/{job.id}/jd")).json()["versions"][0]["version"] == 1
    retried = await client.post(f"{REQ}/{job.id}/jd", json={"role": "Frontend engineer", "expected_version": 1})
    assert retried.status_code == 201, retried.text
    assert retried.json()["versions"][0]["version"] == 2
