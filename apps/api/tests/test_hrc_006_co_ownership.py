"""hrc-006 (DEC-SCOPE-384) -- vacancy co-ownership and assignment history (AC1-AC7, O1-O11). Names are unique per test (the database
is shared and never truncated)."""

import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog, JobAssignment, JobAssignmentHistory, User
from tests.rec001_helpers import as_role, login, make_pm, make_recruiter, make_user
from tests.test_rec_007_requirements import BASE, _company

REASSIGN = "/api/v1/recruiter/manager/reassign"


def _tag() -> str:
    return uuid.uuid4().hex[:8]


async def _world(client, db) -> dict:
    """A manager's recruiter `primary` (signed in) owns a company and a requirement; `mate` is in the same team; `outsider` (another
    team) and the officers `officer` / `officer2` are on nothing yet."""
    manager = await make_pm(db)
    tag = _tag()
    primary = await make_recruiter(db, manager, name=f"Primary {tag}")
    mate = await make_recruiter(db, manager, name=f"Mate {tag}")
    outsider_manager = await make_pm(db)
    outsider = await make_recruiter(db, outsider_manager, name=f"Outsider {tag}")
    officer = await make_user(db, "placement_officer", "it", name=f"Officer {tag}")
    officer2 = await make_user(db, "placement_officer", "it", name=f"Officer2 {tag}")
    company = await _company(db, primary)
    await login(client, primary)
    response = await client.post(BASE, json={"company_id": str(company.id), "title": f"Co-owned {tag}", "location": "Pune"})
    assert response.status_code == 201, response.text
    return {"manager": manager, "primary": primary, "mate": mate, "outsider": outsider, "outsider_manager": outsider_manager, "officer": officer,
            "officer2": officer2, "company": company, "job": response.json()["requirement"]["id"], "tag": tag}  # fmt: skip


async def _add(client, w, who: str, role: str = "collaborator", expected: int = 201) -> dict:
    response = await client.post(f"{BASE}/{w['job']}/assignments", json={"user_id": str(w[who].id), "role": role})
    assert response.status_code == expected, response.text
    return response.json()


async def _history(client, job_id, **params) -> dict:
    response = await client.get(f"{BASE}/{job_id}/assignment-history", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _events(page: dict) -> list[tuple]:
    """Oldest first: (person, role, action, reason)."""
    return [(i["user"]["full_name"], i["role"], i["action"], i["reason"]) for i in reversed(page["items"])]


# --- adding owners (AC5 +, O3, O10, O11) ------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_primary_adds_a_placement_officer_owner_and_a_collaborator(client, db_session):
    w = await _world(client, db_session)
    body = await _add(client, w, "officer", "placement_officer")
    req = (await _add(client, w, "outsider"))["requirement"]
    assert [(o["user"]["id"], o["role"], o["role_label"]) for o in req["owners"]] == [
        (str(w["officer"].id), "placement_officer", "Placement officer owner"),
        (str(w["outsider"].id), "collaborator", "Collaborator"),
    ]
    assert req["owners"][0]["added_by"]["id"] == str(w["primary"].id) and req["owners"][0]["added_at"]
    assert body["requirement"]["permissions"]["can_manage_owners"] is True
    assert req["updated_by"]["id"] == str(w["primary"].id)
    page = await _history(client, w["job"])
    assert _events(page) == [
        (w["primary"].full_name, "primary", "added", None),  # AC3: the create records the primary
        (w["officer"].full_name, "placement_officer", "added", None),
        (w["outsider"].full_name, "collaborator", "added", None),
    ]
    assert all(i["changed_by"]["id"] == str(w["primary"].id) and i["created_at"] for i in page["items"])
    actions = (await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id == w["job"], AuditLog.action.like("%owner%")))).all()
    assert sorted(actions) == ["recruiter_requirement.owner_added"] * 2


@pytest.mark.asyncio
async def test_refusals_two_primaries_two_officer_owners_duplicates_and_bad_targets(client, db_session):
    w = await _world(client, db_session)
    await _add(client, w, "officer", "placement_officer")
    await _add(client, w, "mate", "primary", expected=422)  # AC5 -: there is no second primary
    assert (await _add(client, w, "officer2", "placement_officer", expected=409))["detail"] == "This requirement already has a placement officer owner"
    assert (await _add(client, w, "primary", expected=409))["detail"] == "This person is the primary owner"
    assert (await _add(client, w, "officer", expected=409))["detail"] == "Already an owner of this requirement"
    await _add(client, w, "mate", "placement_officer", expected=422)  # a recruiter is not a placement officer
    w["gone"] = await make_recruiter(db_session, w["manager"], active=False)
    w["hr"] = await make_user(db_session, "hr_manager", "it")
    await _add(client, w, "gone", expected=422)
    await _add(client, w, "hr", expected=422)
    w["nobody"] = User(id=uuid.uuid4())
    await _add(client, w, "nobody", expected=422)
    assert len((await db_session.scalars(select(JobAssignment).where(JobAssignment.job_id == uuid.UUID(w["job"])))).all()) == 1


# --- scope (AC1, AC2, AC6, AC7, O4, O5) -------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_collaborator_from_another_team_reads_and_edits_but_cannot_manage_owners(client, db_session):
    w = await _world(client, db_session)
    await _add(client, w, "outsider")
    await login(client, w["outsider"])
    detail = await client.get(f"{BASE}/{w['job']}")
    assert detail.status_code == 200, detail.text
    perms = detail.json()["requirement"]["permissions"]
    assert perms["can_edit"] and perms["can_view_candidates"] and not perms["can_manage_owners"]
    listed = (await client.get(BASE, params={"q": w["tag"]})).json()
    assert [i["id"] for i in listed["items"]] == [w["job"]]
    assert (await client.patch(f"{BASE}/{w['job']}", json={"location": "Mumbai"})).status_code == 200
    assert (await client.post(f"{BASE}/{w['job']}/status", json={"status": "requirement_received"})).status_code == 200
    assert (await client.get(f"{BASE}/{w['job']}/candidates")).status_code == 200  # a recruiter assignee works the pipeline too
    await _add(client, w, "mate", expected=403)
    assert (await client.delete(f"{BASE}/{w['job']}/assignments/{w['outsider'].id}")).status_code == 403
    assert (await client.get(f"{BASE}/{w['job']}/assignment-options", params={"role": "collaborator"})).status_code == 403
    await login(client, w["outsider_manager"])  # the collaborator's own manager sees the team member's collaboration
    assert (await client.get(f"{BASE}/{w['job']}")).status_code == 200


@pytest.mark.asyncio
async def test_a_placement_officer_owner_reads_and_edits_the_requirement_only(client, db_session):
    w = await _world(client, db_session)
    await _add(client, w, "officer", "placement_officer")
    await login(client, w["officer"])
    assert (await client.get(f"{BASE}/statuses")).status_code == 200
    listed = (await client.get(BASE)).json()
    assert [i["id"] for i in listed["items"]] == [w["job"]] and listed["total"] == 1
    detail = (await client.get(f"{BASE}/{w['job']}")).json()["requirement"]
    assert detail["permissions"]["can_edit"] and not detail["permissions"]["can_view_candidates"] and not detail["permissions"]["can_manage_owners"]
    assert not detail["permissions"]["can_view_matches"] and not detail["permissions"]["can_reassign"]
    assert (await client.patch(f"{BASE}/{w['job']}", json={"location": "Chennai"})).status_code == 200
    assert (await client.post(f"{BASE}/{w['job']}/status", json={"status": "requirement_received"})).status_code == 200
    assert (await client.get(f"{BASE}/{w['job']}/history")).status_code == 200
    assert (await client.get(f"{BASE}/{w['job']}/jd")).status_code == 200
    assert (await client.post(f"{BASE}/{w['job']}/jd", json={"role": "Backend developer"})).status_code == 201
    assert (await client.get(f"{BASE}/{w['job']}/assignment-history")).status_code == 200
    # AC7: no candidate-side route opens for the role (hrc-012 owns candidates)
    for url in (f"{BASE}/{w['job']}/candidates", f"{BASE}/{w['job']}/matches", f"{BASE}/{w['job']}/shares", "/api/v1/recruiter/interviews",
                "/api/v1/recruiter/candidates"):  # fmt: skip
        assert (await client.get(url)).status_code == 403, url
    assert (await client.post(f"{BASE}/{w['job']}/assign", json={"recruiter_user_id": str(w["mate"].id)})).status_code == 403


@pytest.mark.asyncio
async def test_non_assignees_get_404_and_an_unassigned_officer_lists_nothing(client, db_session):
    w = await _world(client, db_session)
    await _add(client, w, "officer", "placement_officer")
    await login(client, w["outsider"])
    for response in (await client.get(f"{BASE}/{w['job']}"), await client.patch(f"{BASE}/{w['job']}", json={"location": "X"}),
                     await client.get(f"{BASE}/{w['job']}/assignment-history")):  # fmt: skip
        assert response.status_code == 404, response.text
    await login(client, w["officer2"])
    assert (await client.get(f"{BASE}/{w['job']}")).status_code == 404
    assert (await client.get(f"{BASE}/{w['job']}/jd")).status_code == 404
    assert (await client.get(BASE, params={"q": w["tag"]})).json()["total"] == 0
    await as_role(client, db_session, "interviewer", "it")
    assert (await client.get(BASE)).status_code == 403  # other recruitment roles stay refused


# --- removing (O6, edge case E) --------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_remove_an_owner_but_never_the_primary(client, db_session):
    w = await _world(client, db_session)
    await _add(client, w, "outsider")
    response = await client.delete(f"{BASE}/{w['job']}/assignments/{w['primary'].id}")
    assert response.status_code == 409 and response.json()["detail"] == "A placement manager must reassign the primary owner first"
    assert (await client.delete(f"{BASE}/{w['job']}/assignments/{w['mate'].id}")).status_code == 404
    response = await client.delete(f"{BASE}/{w['job']}/assignments/{w['outsider'].id}")
    assert response.status_code == 200, response.text
    assert response.json()["requirement"]["owners"] == []
    assert _events(await _history(client, w["job"]))[-1] == (w["outsider"].full_name, "collaborator", "removed", None)
    # a placement manager in scope manages owners too
    await login(client, w["manager"])
    await _add(client, w, "officer", "placement_officer")


# --- primary changes (AC3, AC4, O7, O8) -----------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_reassigning_the_primary_to_a_collaborator_promotes_them(client, db_session):
    w = await _world(client, db_session)
    await _add(client, w, "mate")
    await login(client, w["manager"])
    response = await client.post(f"{BASE}/{w['job']}/assign", json={"recruiter_user_id": str(w["mate"].id)})
    assert response.status_code == 200, response.text
    assert response.json()["requirement"]["owners"] == []
    assert _events(await _history(client, w["job"]))[-3:] == [
        (w["mate"].full_name, "collaborator", "removed", "reassign"),
        (w["primary"].full_name, "primary", "removed", "reassign"),
        (w["mate"].full_name, "primary", "added", "reassign"),
    ]


@pytest.mark.asyncio
async def test_bulk_reassign_moves_the_primary_and_deactivation_releases_collaborations(client, db_session):
    w = await _world(client, db_session)
    await login(client, w["mate"])  # `primary` also collaborates on a requirement of `mate`'s
    other_company = await _company(db_session, w["mate"])
    other = (await client.post(BASE, json={"company_id": str(other_company.id), "title": f"Other {w['tag']}", "location": "Pune"})).json()["requirement"]["id"]
    assert (await client.post(f"{BASE}/{other}/assignments", json={"user_id": str(w["primary"].id), "role": "collaborator"})).status_code == 201
    await login(client, w["manager"])
    response = await client.post(REASSIGN, json={"from_user_id": str(w["primary"].id), "to_user_id": str(w["mate"].id)})
    assert response.status_code == 200, response.text
    assert _events(await _history(client, w["job"]))[-2:] == [
        (w["primary"].full_name, "primary", "removed", "reassign"),
        (w["mate"].full_name, "primary", "added", "reassign"),
    ]
    admin = await as_role(client, db_session, "super_admin", "global")
    response = await client.patch(f"/api/v1/admin/users/{w['primary'].id}", json={"active": False})
    assert response.status_code == 200, response.text
    assert await db_session.scalar(select(JobAssignment.id).where(JobAssignment.user_id == w["primary"].id)) is None
    released = await db_session.scalar(select(JobAssignmentHistory).where(JobAssignmentHistory.job_id == uuid.UUID(other), JobAssignmentHistory.action == "removed"))
    assert (released.user_id, released.role, released.reason, released.changed_by_user_id) == (w["primary"].id, "collaborator", "deactivated", admin.id)


# --- picker and history paging (O11) ---------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_options_list_eligible_active_people_not_already_on_the_job(client, db_session):
    w = await _world(client, db_session)
    await make_recruiter(db_session, w["manager"], name=f"Mate gone {w['tag']}", active=False)
    await _add(client, w, "officer", "placement_officer")
    url = f"{BASE}/{w['job']}/assignment-options"
    names = lambda r: sorted(i["full_name"] for i in r.json()["items"])  # noqa: E731
    response = await client.get(url, params={"role": "collaborator", "q": w["tag"]})
    assert response.status_code == 200, response.text
    assert names(response) == sorted([w["mate"].full_name, w["outsider"].full_name, w["officer2"].full_name])
    assert {i["role"] for i in response.json()["items"]} == {"placement_team", "placement_officer"}
    assert names(await client.get(url, params={"role": "placement_officer", "q": w["tag"]})) == [w["officer2"].full_name]
    assert (await client.get(url, params={"role": "primary"})).status_code == 422


@pytest.mark.asyncio
async def test_history_pages_newest_first(client, db_session):
    w = await _world(client, db_session)
    await _add(client, w, "mate")
    await _add(client, w, "outsider")
    first = await _history(client, w["job"], limit=2)
    assert first["total"] == 3 and len(first["items"]) == 2 and first["items"][0]["user"]["id"] == str(w["outsider"].id)
    assert first["items"][0]["role_label"] == "Collaborator"
    rest = await _history(client, w["job"], limit=2, offset=2)
    assert [i["role"] for i in rest["items"]] == ["primary"]
