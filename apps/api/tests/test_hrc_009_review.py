"""hrc-009 (DEC-SCOPE-390) -- eligibility-change review and vacancy-change notices (AC1-AC5, R1-R9). Names are unique per test (the
database is shared and never truncated)."""

import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog, JobApplication, Notification
from app.notifications.events import notify
from tests.rec001_helpers import login, make_pm, make_recruiter, make_user
from tests.rec017_helpers import student_application
from tests.test_emp_002_job_posting import _create_student, _register_employer
from tests.test_rec_007_requirements import BASE, _company
from tests.test_rec_017_tracking import _candidate

APPS = "/api/v1/recruiter/applications"
EVENT = "it.requirement.review_needed"


def _tag() -> str:
    return uuid.uuid4().hex[:8]


async def _world(client, db, *, open_apps: bool = True) -> dict:
    """The signed-in primary recruiter owns a requirement (one required skill, 12-36 months, B.Tech, Pune) with a collaborator and a
    placement-officer owner; candidates `a` (Sourced) and `b` (Shortlisted) are open, `c` is Rejected."""
    manager = await make_pm(db)
    tag = _tag()
    primary = await make_recruiter(db, manager, name=f"Primary {tag}")
    mate = await make_recruiter(db, manager, name=f"Mate {tag}")
    officer = await make_user(db, "placement_officer", "it", name=f"Officer {tag}")
    company = await _company(db, primary)
    await login(client, primary)
    response = await client.post(BASE, json={
        "company_id": str(company.id), "title": f"Review {tag}", "location": "Pune", "description": "Old text", "qualification": "B.Tech",
        "experience_min_months": 12, "experience_max_months": 36, "required_skills": [f"Py{tag}"], "preferred_skills": [f"Kube{tag}"],
    })
    assert response.status_code == 201, response.text
    job = response.json()["requirement"]
    for who, role in ((mate, "collaborator"), (officer, "placement_officer")):
        added = await client.post(f"{BASE}/{job['id']}/assignments", json={"user_id": str(who.id), "role": role})
        assert added.status_code == 201, added.text
    apps = {}
    if open_apps:
        for key, status in (("a", "sourced"), ("b", "shortlisted"), ("c", "sourced")):
            candidate = await _candidate(db, primary)
            added = await client.post(f"{BASE}/{job['id']}/candidates", json={"candidate_id": str(candidate.id), "status": status})
            assert added.status_code == 201, added.text
            apps[key] = added.json()["application"]["id"]
        moved = await client.post(f"{APPS}/{apps['c']}/status", json={"status": "rejected"})
        assert moved.status_code == 200, moved.text
    ids = {f"{k}_id": str(v.id) for k, v in (("primary", primary), ("mate", mate), ("officer", officer))}  # stable after expire_all()
    return {"manager": manager, "primary": primary, "mate": mate, "officer": officer, "job": job["id"], "apps": apps, "tag": tag, **ids}


async def _patch(client, w, body: dict) -> dict:
    response = await client.patch(f"{BASE}/{w['job']}", json=body)
    assert response.status_code == 200, response.text
    return response.json()["requirement"]


async def _flags(db, w) -> dict:
    db.expire_all()
    rows = (await db.execute(select(JobApplication.id, JobApplication.needs_review_since, JobApplication.status)
                             .where(JobApplication.id.in_([uuid.UUID(i) for i in w["apps"].values()])))).all()  # fmt: skip
    by_id = {str(i): (since is not None, status) for i, since, status in rows}
    return {key: by_id[i] for key, i in w["apps"].items()}


async def _notices(db, w) -> list[tuple]:
    rows = (await db.execute(select(Notification.user_id, Notification.body, Notification.action_url)
                             .where(Notification.event_type == EVENT, Notification.entity_id == w["job"]))).all()  # fmt: skip
    return sorted((str(u), b, url) for u, b, url in rows)


def _expected(w, count: int) -> list[tuple]:
    body = f"Applications to review: {count}. A vacancy's eligibility criteria changed. Open EduSphere to confirm or move them."
    return sorted((w[f"{k}_id"], body, f"/recruiter/requirements/{w['job']}") for k in ("mate", "officer"))


# --- AC1, AC3, AC5: a required-skill change flags the open applications and notifies the other owners once --------------------------
@pytest.mark.asyncio
async def test_a_required_skill_change_flags_open_applications_and_notifies_owners_once(client, db_session):
    w = await _world(client, db_session)
    await _patch(client, w, {"required_skills": [f"Py{w['tag']}", f"Go{w['tag']}"]})
    assert await _flags(db_session, w) == {"a": (True, "sourced"), "b": (True, "shortlisted"), "c": (False, "rejected")}  # AC5: no move
    assert await _notices(db_session, w) == _expected(w, 2)  # R5: not the editor; one each


# --- AC2: a cosmetic change flags nothing -------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cosmetic_and_preferred_skill_changes_flag_nothing(client, db_session):
    w = await _world(client, db_session)
    await _patch(client, w, {"description": "New text", "title": f"Renamed {w['tag']}", "salary_min": 100, "salary_max": 200,
                             "preferred_skills": [f"Docker{w['tag']}"], "required_skills": [f"py{w['tag']}"]})  # fmt: skip
    assert await _flags(db_session, w) == {"a": (False, "sourced"), "b": (False, "shortlisted"), "c": (False, "rejected")}
    assert await _notices(db_session, w) == []


# --- R1: every eligibility criterion -----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    {"experience_min_months": 24}, {"experience_max_months": None}, {"qualification": "M.Tech"}, {"location": "Chennai"},
    {"work_mode": "remote"},
])  # fmt: skip
async def test_each_eligibility_criterion_flags(client, db_session, body):
    w = await _world(client, db_session)
    await _patch(client, w, body)
    assert (await _flags(db_session, w))["a"] == (True, "sourced")
    assert await _notices(db_session, w) == _expected(w, 2)


@pytest.mark.asyncio
async def test_a_qualification_case_change_is_not_a_change_of_eligibility(client, db_session):
    w = await _world(client, db_session)
    await _patch(client, w, {"qualification": "b.tech"})
    assert (await _flags(db_session, w))["a"] == (False, "sourced")


# --- E: no open applications, and an application already flagged -------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_job_without_open_applications_sends_no_notice(client, db_session):
    w = await _world(client, db_session, open_apps=False)
    await _patch(client, w, {"qualification": "M.Tech"})
    assert await _notices(db_session, w) == []


@pytest.mark.asyncio
async def test_already_flagged_applications_are_not_counted_or_notified_again(client, db_session):
    w = await _world(client, db_session)
    await _patch(client, w, {"qualification": "M.Tech"})
    first = (await db_session.scalars(select(JobApplication.needs_review_since).where(JobApplication.id == uuid.UUID(w["apps"]["a"])))).one()
    await _patch(client, w, {"qualification": "MBA"})
    db_session.expire_all()
    again = (await db_session.scalars(select(JobApplication.needs_review_since).where(JobApplication.id == uuid.UUID(w["apps"]["a"])))).one()
    assert again == first  # R3: the first time stays
    assert await _notices(db_session, w) == _expected(w, 2)


# --- R8: the review list ------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_review_list_and_count(client, db_session):
    w = await _world(client, db_session)
    listed = (await client.get(f"{BASE}/{w['job']}/candidates")).json()
    assert listed["needs_review_count"] == 0 and all(i["needs_review_since"] is None for i in listed["items"])
    await _patch(client, w, {"location": "Chennai"})
    listed = (await client.get(f"{BASE}/{w['job']}/candidates")).json()
    assert listed["needs_review_count"] == 2 and len(listed["items"]) == 3
    review = (await client.get(f"{BASE}/{w['job']}/candidates", params={"needs_review": "true"})).json()
    assert sorted(i["id"] for i in review["items"]) == sorted([w["apps"]["a"], w["apps"]["b"]])
    assert all(i["needs_review_since"] for i in review["items"]) and review["needs_review_count"] == 2


# --- R4, R9: confirm or move ----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_confirm_clears_the_flag_without_a_move_and_is_audited(client, db_session):
    w = await _world(client, db_session)
    await _patch(client, w, {"qualification": "M.Tech"})
    response = await client.post(f"{APPS}/{w['apps']['a']}/confirm-review")
    assert response.status_code == 200, response.text
    item = response.json()["application"]
    assert item["needs_review_since"] is None and item["status"] == "sourced"
    assert (await _flags(db_session, w))["a"] == (False, "sourced")
    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == w["apps"]["a"], AuditLog.action == "recruiter_application.review_confirmed"))).all()
    assert len(audit) == 1 and str(audit[0].user_id) == w["primary_id"]
    again = await client.post(f"{APPS}/{w['apps']['a']}/confirm-review")
    assert again.status_code == 409 and again.json()["detail"] == "This application does not need a review"


@pytest.mark.asyncio
async def test_a_status_move_clears_the_flag(client, db_session):
    w = await _world(client, db_session)
    await _patch(client, w, {"qualification": "M.Tech"})
    moved = await client.post(f"{APPS}/{w['apps']['b']}/status", json={"status": "rejected"})
    assert moved.status_code == 200 and moved.json()["application"]["needs_review_since"] is None
    assert (await _flags(db_session, w))["b"] == (False, "rejected")


@pytest.mark.asyncio
async def test_only_writers_confirm_and_out_of_scope_is_404(client, db_session):
    w = await _world(client, db_session)
    await _patch(client, w, {"qualification": "M.Tech"})
    await login(client, w["manager"])  # a reader of the requirement's candidates
    assert (await client.get(f"{BASE}/{w['job']}/candidates", params={"needs_review": "true"})).status_code == 200
    refused = await client.post(f"{APPS}/{w['apps']['a']}/confirm-review")
    assert refused.status_code == 403
    stranger = await make_recruiter(db_session, await make_pm(db_session))
    await login(client, stranger)
    assert (await client.post(f"{APPS}/{w['apps']['a']}/confirm-review")).status_code == 404
    assert (await client.get(f"{BASE}/{w['job']}/candidates", params={"needs_review": "true"})).status_code == 404
    assert (await _flags(db_session, w))["a"] == (True, "sourced")


# --- R7: the employer's edit path ---------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_an_employer_skill_edit_flags_the_open_applications(client, db_session):
    await _register_employer(client)
    job = (await client.post("/api/v1/employer/jobs", json={"title": f"Emp {_tag()}", "location": "Pune", "description": "d", "skills": ["Java"]})).json()
    student = await _create_student(db_session)
    application_id = (await student_application(db_session, uuid.UUID(job["id"]), student)).id
    await db_session.commit()
    cosmetic = await client.patch(f"/api/v1/employer/jobs/{job['id']}", json={"description": "new"})
    assert cosmetic.status_code == 200, cosmetic.text
    db_session.expire_all()
    assert (await db_session.get(JobApplication, application_id)).needs_review_since is None
    edited = await client.patch(f"/api/v1/employer/jobs/{job['id']}", json={"skills": ["Java", "Spring"]})
    assert edited.status_code == 200, edited.text
    db_session.expire_all()
    assert (await db_session.get(JobApplication, application_id)).needs_review_since is not None


# --- R6: the count is the only variable text --------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_notify_count_fills_only_a_counted_event(db_session):
    with pytest.raises(ValueError):
        await notify(db_session, [], "it.candidate.assigned", uuid.uuid4(), count=3)
    with pytest.raises(ValueError):
        await notify(db_session, [], EVENT, uuid.uuid4())
