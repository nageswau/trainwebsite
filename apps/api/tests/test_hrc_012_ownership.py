"""hrc-012 (DEC-SCOPE-381, spec docs/superpowers/specs/2026-11-04-hrc-012-candidate-ownership-design.md): one primary recruiter (O2,
AC1), a placement-officer owner (O3), collaborators only while shared ownership is on (O4, AC2), who may change them (O5), the history
(O6, AC3), the owner on create (O7), the deactivated recruiter's candidates moving with rec-037's reassign (O8, AC4) and the notices (O10).
Visibility stays pool-wide (O1)."""

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import AuditLog, CandidateAssignmentHistory, CandidateOwnershipSetting, Notification, User
from tests.rec038_helpers import _recruiter, _user, make_candidate, tag
from tests.tel026_helpers import headers

pytestmark = pytest.mark.asyncio
CANDIDATES = "/api/v1/recruiter/candidates"
SETTINGS = "/api/v1/recruiter/candidate-ownership-settings"
REASSIGN = "/api/v1/recruiter/manager/reassign"
TEAM = "/api/v1/recruiter/manager/team"


@pytest_asyncio.fixture
async def shared(db_session):
    """Switches shared ownership on for one test and restores the stored value after (the setting is one global row)."""
    row = await db_session.get(CandidateOwnershipSetting, 1)
    before = row.shared_ownership if row else None
    if row is None:
        row = CandidateOwnershipSetting(id=1, shared_ownership=True)
        db_session.add(row)
    row.shared_ownership = True
    await db_session.commit()
    yield
    row = await db_session.get(CandidateOwnershipSetting, 1)
    if before is None:
        await db_session.delete(row)
    else:
        row.shared_ownership = before
    await db_session.commit()


@pytest_asyncio.fixture
async def unshared(db_session):
    row = await db_session.get(CandidateOwnershipSetting, 1)
    before = row.shared_ownership if row else None
    if row is not None:
        row.shared_ownership = False
        await db_session.commit()
    yield
    if row is not None:
        row = await db_session.get(CandidateOwnershipSetting, 1)
        row.shared_ownership = before
        await db_session.commit()


async def _world(db):
    manager = await _user(db, "placement_manager", "global")
    rec, rec2 = await _recruiter(db, manager), await _recruiter(db, manager)
    officer = await _user(db, "placement_officer", "it")
    candidate = await make_candidate(db, rec, owner_user_id=rec.id)
    await db.commit()
    return manager, rec, rec2, officer, candidate


async def _committed(db, role: str, division: str) -> User:
    user = await _user(db, role, division)
    await db.commit()
    return user


async def _source(db) -> str:
    from app.models import RecCandidateSource

    return str(await db.scalar(select(RecCandidateSource.id).where(RecCandidateSource.name == "Referral")))


async def _put(client, user, candidate_id, body, expected=200) -> dict:
    response = await client.put(f"{CANDIDATES}/{candidate_id}/ownership", json=body, headers=headers(user))
    assert response.status_code == expected, response.text
    return response.json()


async def _history(db, candidate_id) -> list[CandidateAssignmentHistory]:
    return (await db.scalars(select(CandidateAssignmentHistory).where(CandidateAssignmentHistory.candidate_id == candidate_id)
                             .order_by(CandidateAssignmentHistory.created_at, CandidateAssignmentHistory.kind))).all()  # fmt: skip


# --- O7: the owner on create ---------------------------------------------------------------------------------------------------
async def test_a_recruiter_who_adds_a_candidate_owns_it_and_a_manager_leaves_it_unassigned(client, db_session):
    manager, rec, *_ = await _world(db_session)
    body = {"name": f"Asha {tag()}", "email": f"{tag('h12-')}@example.com", "source_id": await _source(db_session)}
    created = await client.post(CANDIDATES, json=body, headers=headers(rec))
    assert created.status_code == 201, created.text
    ownership = created.json()["ownership"]
    assert ownership["owner"] == {"id": str(rec.id), "full_name": rec.full_name, "active": True}
    assert ownership["placement_officer"] is None and ownership["collaborators"] == [] and ownership["can_assign"] is True
    [row] = await _history(db_session, created.json()["id"])
    assert (row.kind, row.from_user_id, row.to_user_id, row.reason) == ("owner", None, rec.id, "create")

    body = {"name": f"Ravi {tag()}", "email": f"{tag('h12-')}@example.com", "source_id": await _source(db_session)}
    by_manager = await client.post(CANDIDATES, json=body, headers=headers(manager))
    assert by_manager.json()["ownership"]["owner"] is None
    assert await _history(db_session, by_manager.json()["id"]) == []


# --- O1: list filter and owner on each item -----------------------------------------------------------------------------------
async def test_list_shows_the_owner_and_filters_my_candidates_and_unassigned(client, db_session):
    manager, rec, rec2, officer, mine = await _world(db_session)
    unassigned = await make_candidate(db_session, manager)
    theirs = await make_candidate(db_session, rec2, owner_user_id=rec2.id)
    officer_only = await make_candidate(db_session, rec2, owner_user_id=rec2.id, placement_officer_user_id=officer.id)
    await db_session.commit()

    async def ids(user, **params) -> set[str]:
        response = await client.get(CANDIDATES, params={"limit": 100, **params}, headers=headers(user))
        assert response.status_code == 200, response.text
        return {c["id"] for c in response.json()["items"]}

    everyone = await ids(rec)  # O1: still pool-wide
    assert {str(mine.id), str(theirs.id)} <= everyone
    assert await ids(rec, owner="me") >= {str(mine.id)} and str(theirs.id) not in await ids(rec, owner="me")
    unassigned_ids = await ids(rec, owner="unassigned", q=unassigned.candidate_code)
    assert unassigned_ids == {str(unassigned.id)}
    assert str(mine.id) not in await ids(rec, owner="unassigned", q=mine.candidate_code)
    response = await client.get(CANDIDATES, params={"q": mine.candidate_code}, headers=headers(rec))
    assert response.json()["items"][0]["owner"] == {"id": str(rec.id), "full_name": rec.full_name, "active": True}
    response = await client.get(CANDIDATES, params={"q": officer_only.candidate_code, "owner": "me"}, headers=headers(rec2))
    assert [c["id"] for c in response.json()["items"]] == [str(officer_only.id)]
    assert (await client.get(CANDIDATES, params={"owner": "someone"}, headers=headers(rec))).status_code == 422


# --- O2/O5/O6: reassign rights, eligibility, history, audit, notice -----------------------------------------------------------
async def test_the_owner_reassigns_with_history_audit_and_a_notice_to_the_new_owner(client, db_session):
    _, rec, rec2, _, candidate = await _world(db_session)
    detail = await _put(client, rec, candidate.id, {"owner_user_id": str(rec2.id)})
    assert detail["ownership"]["owner"]["id"] == str(rec2.id) and detail["ownership"]["can_assign"] is False  # no longer the owner
    [row] = await _history(db_session, candidate.id)
    assert (row.kind, row.from_user_id, row.to_user_id, row.changed_by_user_id, row.reason) == ("owner", rec.id, rec2.id, rec.id, "assign")
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(candidate.id), AuditLog.action == "candidate.assign"))
    assert audit.metadata_json["changes"] == {"primary recruiter": [rec.full_name, rec2.full_name]}
    notices = (await db_session.scalars(select(Notification).where(Notification.entity_id == str(candidate.id)))).all()
    assert [(n.user_id, n.event_type, n.title) for n in notices] == [(rec2.id, "it.candidate.assigned", "Candidate assigned to you")]
    # the former owner may not take it back; the new one may
    await _put(client, rec, candidate.id, {"owner_user_id": str(rec.id)}, 403)
    await _put(client, rec2, candidate.id, {"owner_user_id": str(rec.id)})


async def test_managers_and_super_admin_assign_any_candidate_others_are_refused(client, db_session):
    manager, rec, rec2, _, candidate = await _world(db_session)
    unassigned = await make_candidate(db_session, manager)
    await db_session.commit()
    await _put(client, manager, unassigned.id, {"owner_user_id": str(rec.id)})
    await _put(client, await _committed(db_session, "super_admin", "global"), candidate.id, {"owner_user_id": str(rec2.id)})
    for role, division in (("hr_team", "it"), ("hr_manager", "it"), ("placement_officer", "it"), ("it_admin", "it")):
        await _put(client, await _committed(db_session, role, division), candidate.id, {"owner_user_id": str(rec.id)}, 403)
    other = await _recruiter(db_session, manager)
    await db_session.commit()
    await _put(client, other, unassigned.id, {"owner_user_id": str(other.id)}, 403)  # an unassigned candidate is not up for grabs
    assert (await client.put(f"{CANDIDATES}/{candidate.id}/ownership", json={})).status_code == 401


async def test_an_inactive_or_wrong_role_target_is_422_and_nothing_changes(client, db_session):
    manager, rec, _, officer, candidate = await _world(db_session)
    inactive = await _recruiter(db_session, manager)
    inactive.active = False
    await db_session.commit()
    for target in (inactive, officer, manager):
        body = await _put(client, rec, candidate.id, {"owner_user_id": str(target.id)}, 422)
        assert body["detail"] == "Choose an active recruiter"
    assert (await _put(client, rec, candidate.id, {"placement_officer_user_id": str(rec.id)}, 422))["detail"] == "Choose an active placement officer"
    assert (await _put(client, rec, candidate.id, {"owner_user_id": None}, 422))["detail"] == "A candidate keeps one primary recruiter"
    assert (await _put(client, rec, candidate.id, {"owner_user_id": "nope"}, 422))["detail"]
    assert await _history(db_session, candidate.id) == []


async def test_placement_officer_is_set_and_cleared_and_sees_the_count_on_their_dashboard(client, db_session):
    _, rec, _, officer, candidate = await _world(db_session)
    detail = await _put(client, rec, candidate.id, {"placement_officer_user_id": str(officer.id)})
    assert detail["ownership"]["placement_officer"] == {"id": str(officer.id), "full_name": officer.full_name, "active": True}
    dashboard = await client.get("/api/v1/portal/it/placement-officer/dashboard", headers=headers(officer))
    assert dashboard.status_code == 200, dashboard.text
    assert {"label": "Your candidates", "value": 1} in dashboard.json()["metrics"]
    detail = await _put(client, rec, candidate.id, {"placement_officer_user_id": None})
    assert detail["ownership"]["placement_officer"] is None
    kinds = [(h.kind, h.from_user_id, h.to_user_id) for h in await _history(db_session, candidate.id)]
    assert kinds == [("placement_officer", None, officer.id), ("placement_officer", officer.id, None)]


async def test_a_no_op_put_writes_nothing_and_archived_is_409(client, db_session):
    _, rec, _, _, candidate = await _world(db_session)
    await _put(client, rec, candidate.id, {"owner_user_id": str(rec.id), "placement_officer_user_id": None, "collaborator_user_ids": []})
    assert await _history(db_session, candidate.id) == []
    archived = await client.post(f"{CANDIDATES}/{candidate.id}/archive", headers=headers(rec))
    assert archived.status_code == 200
    await _put(client, rec, candidate.id, {"placement_officer_user_id": None}, 409)


# --- O4: collaborators and the setting (AC2) ------------------------------------------------------------------------------------
async def test_collaborators_are_refused_while_shared_ownership_is_off(client, db_session, unshared):
    _, rec, rec2, _, candidate = await _world(db_session)
    body = await _put(client, rec, candidate.id, {"collaborator_user_ids": [str(rec2.id)]}, 422)
    assert body["detail"] == "Shared ownership is switched off"
    detail = (await client.get(f"{CANDIDATES}/{candidate.id}", headers=headers(rec))).json()
    assert detail["ownership"]["shared_ownership"] is False


async def test_collaborators_when_shared_ownership_is_on(client, db_session, shared):
    _, rec, rec2, officer, candidate = await _world(db_session)
    detail = await _put(client, rec, candidate.id, {"collaborator_user_ids": [str(rec2.id), str(officer.id)]})
    assert {c["id"] for c in detail["ownership"]["collaborators"]} == {str(rec2.id), str(officer.id)}
    assert detail["ownership"]["shared_ownership"] is True
    assert (await _put(client, rec, candidate.id, {"collaborator_user_ids": [str(rec.id)]}, 422))["detail"] == "The primary recruiter is already an owner"
    assert (await _put(client, rec, candidate.id, {"collaborator_user_ids": [str(rec2.id)] * 2 + [str(rec.id)] * 10}, 422))["detail"]
    # a collaborator sees it under My candidates but may not reassign
    mine = await client.get(CANDIDATES, params={"owner": "me", "q": candidate.candidate_code}, headers=headers(rec2))
    assert [c["id"] for c in mine.json()["items"]] == [str(candidate.id)]
    await _put(client, rec2, candidate.id, {"owner_user_id": str(rec2.id)}, 403)
    detail = await _put(client, rec, candidate.id, {"collaborator_user_ids": [str(officer.id)]})
    assert [c["id"] for c in detail["ownership"]["collaborators"]] == [str(officer.id)]
    kinds = sorted((h.kind, h.to_user_id or h.from_user_id) for h in await _history(db_session, candidate.id))
    assert kinds == sorted([("collaborator_added", rec2.id), ("collaborator_added", officer.id), ("collaborator_removed", rec2.id)])
    # making a collaborator the primary owner drops their collaborator row
    detail = await _put(client, rec, candidate.id, {"owner_user_id": str(rec2.id), "collaborator_user_ids": [str(officer.id), str(rec.id)]})
    assert detail["ownership"]["owner"]["id"] == str(rec2.id)
    assert {c["id"] for c in detail["ownership"]["collaborators"]} == {str(officer.id), str(rec.id)}


async def test_removing_collaborators_works_after_the_setting_is_switched_off(client, db_session, shared):
    _, rec, rec2, _, candidate = await _world(db_session)
    await _put(client, rec, candidate.id, {"collaborator_user_ids": [str(rec2.id)]})
    row = await db_session.get(CandidateOwnershipSetting, 1)
    row.shared_ownership = False
    await db_session.commit()
    detail = await _put(client, rec, candidate.id, {"collaborator_user_ids": []})
    assert detail["ownership"]["collaborators"] == []


async def test_settings_are_read_by_candidate_readers_and_changed_by_managers(client, db_session, unshared):
    manager, rec, *_ = await _world(db_session)
    got = await client.get(SETTINGS, headers=headers(rec))
    assert got.status_code == 200 and got.json() == {"shared_ownership": False, "can_edit": False}
    assert (await client.put(SETTINGS, json={"shared_ownership": True}, headers=headers(rec))).status_code == 403
    assert (await client.get(SETTINGS, headers=headers(await _committed(db_session, "interviewer", "it")))).status_code == 403
    put = await client.put(SETTINGS, json={"shared_ownership": True}, headers=headers(manager))
    assert put.status_code == 200 and put.json() == {"shared_ownership": True, "can_edit": True}
    assert (await client.put(SETTINGS, json={"shared_ownership": "maybe"}, headers=headers(manager))).status_code == 422
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "candidate.ownership_settings", AuditLog.user_id == manager.id))
    assert audit.metadata_json == {"shared_ownership": True}
    await client.put(SETTINGS, json={"shared_ownership": False}, headers=headers(manager))


async def test_assignee_lookup_returns_active_eligible_people_only(client, db_session):
    manager, rec, rec2, officer, _ = await _world(db_session)
    url = f"{CANDIDATES}/assignees"
    found = await client.get(url, params={"kind": "recruiter", "q": rec2.full_name}, headers=headers(rec))
    assert found.status_code == 200, found.text
    assert found.json() == [{"id": str(rec2.id), "full_name": rec2.full_name, "role": "placement_team"}]
    assert (await client.get(url, params={"kind": "recruiter", "q": officer.full_name}, headers=headers(rec))).json() == []
    assert [p["id"] for p in (await client.get(url, params={"kind": "officer", "q": officer.full_name}, headers=headers(rec))).json()] == [str(officer.id)]
    both = await client.get(url, params={"kind": "collaborator", "q": officer.full_name}, headers=headers(rec))
    assert [p["role"] for p in both.json()] == ["placement_officer"]
    assert (await client.get(url, params={"kind": "recruiter"}, headers=headers(await _committed(db_session, "hr_team", "it")))).status_code == 403
    assert (await client.get(url, params={"kind": "other"}, headers=headers(rec))).status_code == 422


# --- O8: deactivation and rec-037's reassign (AC4) -------------------------------------------------------------------------------
async def test_a_recruiter_owning_candidates_cannot_be_deactivated_until_the_team_reassign_moves_them(client, db_session):
    manager, rec, rec2, _, candidate = await _world(db_session)
    archived = await make_candidate(db_session, rec, owner_user_id=rec.id)
    from datetime import UTC, datetime

    archived.archived_at = datetime.now(UTC)
    await db_session.commit()
    admin = await _committed(db_session, "super_admin", "global")
    refused = await client.patch(f"/api/v1/admin/users/{rec.id}", json={"active": False}, headers=headers(admin))
    assert refused.status_code == 422, refused.text
    assert refused.json()["detail"] == "This recruiter has 1 candidate. A placement manager must reassign them (Team page) before deactivation."

    team = await client.get(TEAM, params={"limit": 100}, headers=headers(manager))
    row = next(r for r in team.json()["items"] if r["id"] == str(rec.id))
    assert row["work"] == {"companies": 0, "requirements": 0, "follow_ups": 0, "candidates": 2}
    moved = await client.post(REASSIGN, json={"from_user_id": str(rec.id), "to_user_id": str(rec2.id)}, headers=headers(manager))
    assert moved.status_code == 200, moved.text
    assert moved.json()["moved"] == {"companies": 0, "requirements": 0, "follow_ups": 0, "candidates": 2}
    rows = await _history(db_session, candidate.id)
    assert [(h.kind, h.from_user_id, h.to_user_id, h.reason) for h in rows] == [("owner", rec.id, rec2.id, "reassign")]
    ok = await client.patch(f"/api/v1/admin/users/{rec.id}", json={"active": False}, headers=headers(admin))
    assert ok.status_code == 200, ok.text
    assert await db_session.scalar(select(User.active).where(User.id == rec.id)) is False
