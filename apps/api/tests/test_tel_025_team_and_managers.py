"""tel-025 -- POST /admin/telecallers/{id}/move-team (T22, D2), the telecaller manager deactivation (D4) and the plain-PATCH guard (D5)."""

import uuid

import pytest
from sqlalchemy import select

from app.models import Enquiry, TelDistributionRule, TelecallerProfile, User
from tests.tel016_helpers import make_counselor
from tests.tel025_helpers import (
    MANAGERS,
    TELECALLERS,
    as_user,
    audit_rows,
    fresh,
    lead,
    make_telecaller,
    make_tl_manager,
    make_user,
    post,
    rule_for,
    team,
)

USERS = "/api/v1/admin/users"


def move_url(user_id) -> str:
    return f"{TELECALLERS}/{user_id}/move-team"


async def _profile(db, user_id) -> TelecallerProfile:
    return await db.scalar(select(TelecallerProfile).where(TelecallerProfile.user_id == user_id).execution_options(populate_existing=True))


# --- move team ---------------------------------------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_move_team_hands_open_leads_to_the_old_team_and_moves_the_division(client, db_session):
    _, a, b = await team(db_session)
    one = await lead(db_session, telecaller=a, status="contacted")
    closed = await lead(db_session, telecaller=a, status="lost")
    a_rule = await rule_for(db_session, a)
    new_manager = await make_tl_manager(db_session)
    await as_user(client, a)
    a_cookie = client.cookies.get("edusphere_access")
    admin = await make_user(db_session, "super_admin", "global")
    await as_user(client, admin)

    response = await post(client, move_url(a.id), {"team": "overseas", "target": "telecaller", "reassign_to": str(b.id),
                                                   "reporting_manager_user_id": str(new_manager.id)})
    assert response.status_code == 200, response.text
    assert response.json() == {"id": str(a.id), "team": "overseas", "target": "telecaller",
                               "moved": {"leads": 1, "follow_ups": 0, "appointments": 0}, "rules_removed": 1}
    profile = await _profile(db_session, a.id)
    moved_user = await fresh(db_session, User, a.id)
    assert (profile.team, moved_user.division, moved_user.active) == ("overseas", "overseas", True)
    assert profile.reporting_manager_user_id == new_manager.id
    assert (await fresh(db_session, Enquiry, one.id)).telecaller_user_id == b.id
    assert (await fresh(db_session, Enquiry, closed.id)).telecaller_user_id == a.id  # AC2
    assert await db_session.get(TelDistributionRule, a_rule.id, populate_existing=True) is None
    [audit] = await audit_rows(db_session, "telecaller.move_team", a.id)
    assert audit.metadata_json["from_team"] == "it" and audit.metadata_json["to_team"] == "overseas"
    [assign] = await audit_rows(db_session, "lead.assign", one.id)
    assert assign.metadata_json["method"] == "team_move"
    # D2: the division in the old token is wrong now; the session ends
    client.cookies.clear()
    client.cookies.set("edusphere_access", a_cookie)
    assert (await client.get("/api/v1/telecaller/me")).status_code == 401


@pytest.mark.asyncio
async def test_move_team_rules(client, db_session):
    manager, a, _ = await team(db_session)
    await lead(db_session, telecaller=a)
    overseas_tel = await make_telecaller(db_session, manager, team="overseas")
    await as_user(client, await make_user(db_session, "super_admin", "global"))
    # backlog negative: the new owner must be on the OLD team (the leads stay in their division)
    response = await post(client, move_url(a.id), {"team": "overseas", "target": "telecaller", "reassign_to": str(overseas_tel.id)})
    assert response.status_code == 422 and response.json()["detail"] == "Choose an active telecaller of the same team"
    assert (await post(client, move_url(a.id), {"team": "overseas"})).status_code == 422  # open work, no target (AC3)
    assert (await post(client, move_url(a.id), {"team": "it", "target": "queue"})).status_code == 422  # same team
    assert (await post(client, move_url(a.id), {"team": "mars", "target": "queue"})).status_code == 422
    inactive_mgr = await make_tl_manager(db_session, active=False)
    bad_mgr = await post(client, move_url(a.id), {"team": "overseas", "target": "queue", "reporting_manager_user_id": str(inactive_mgr.id)})
    assert bad_mgr.status_code == 422
    assert (await _profile(db_session, a.id)).team == "it"
    ok = await post(client, move_url(a.id), {"team": "overseas", "target": "queue"})
    assert ok.status_code == 200, ok.text
    assert (await _profile(db_session, a.id)).reporting_manager_user_id == manager.id  # kept when not given


@pytest.mark.asyncio
async def test_a_division_admin_cannot_move_teams(client, db_session):
    """LC1: a move spans two teams; an IT admin covers one."""
    _, a, _ = await team(db_session)
    await as_user(client, await make_user(db_session, "it_admin", "it"))
    response = await post(client, move_url(a.id), {"team": "overseas"})
    assert response.status_code == 403
    assert (await _profile(db_session, a.id)).team == "it"


# --- telecaller manager deactivation ----------------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_manager_with_reports_needs_a_replacement(client, db_session):
    manager, a, b = await team(db_session)
    b.active = False  # an inactive report moves too (it may be reactivated under the new manager)
    await db_session.commit()
    replacement = await make_tl_manager(db_session)
    admin = await make_user(db_session, "super_admin", "global")
    await as_user(client, admin)
    listed = (await client.get(MANAGERS, params={"q": manager.email})).json()["items"]
    assert [(x["id"], x["telecaller_count"]) for x in listed] == [(str(manager.id), 2)]
    refused = await post(client, f"{MANAGERS}/{manager.id}/deactivate", {})
    assert refused.status_code == 422 and (await fresh(db_session, User, manager.id)).active is True
    for bad in (manager.id, a.id, uuid.uuid4(), (await make_tl_manager(db_session, active=False)).id):
        assert (await post(client, f"{MANAGERS}/{manager.id}/deactivate", {"reassign_to": str(bad)})).status_code == 422

    response = await post(client, f"{MANAGERS}/{manager.id}/deactivate", {"reassign_to": str(replacement.id)})
    assert response.status_code == 200, response.text
    assert response.json() == {"id": str(manager.id), "active": False, "moved_telecallers": 2}
    for t in (a, b):
        assert (await _profile(db_session, t.id)).reporting_manager_user_id == replacement.id
    assert len(await audit_rows(db_session, "telecaller_manager.deactivate", manager.id)) == 1
    assert (await post(client, f"{MANAGERS}/{manager.id}/deactivate", {})).status_code == 409


@pytest.mark.asyncio
async def test_manager_deactivation_scope(client, db_session):
    manager = await make_tl_manager(db_session)
    await as_user(client, await make_user(db_session, "it_admin", "it"))
    assert (await post(client, f"{MANAGERS}/{manager.id}/deactivate", {})).status_code == 403
    await as_user(client, await make_user(db_session, "super_admin", "global"))
    assert (await post(client, f"{MANAGERS}/{uuid.uuid4()}/deactivate", {})).status_code == 404
    response = await post(client, f"{MANAGERS}/{manager.id}/deactivate", {})  # no reports: no replacement needed
    assert response.status_code == 200 and response.json()["moved_telecallers"] == 0


# --- PATCH /admin/users guard (D5) -----------------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_plain_patch_refuses_a_telecaller_with_open_leads(client, db_session):
    manager, a, b = await team(db_session)
    await lead(db_session, telecaller=a)
    await as_user(client, await make_user(db_session, "super_admin", "global"))
    response = await client.patch(f"{USERS}/{a.id}", json={"active": False})
    assert response.status_code == 422
    assert "Telecallers page" in response.json()["detail"]
    assert (await fresh(db_session, User, a.id)).active is True
    # no open work: allowed, and the session ends (D5)
    before = b.session_version
    assert (await client.patch(f"{USERS}/{b.id}", json={"active": False})).status_code == 200
    b_now = await fresh(db_session, User, b.id)
    assert b_now.active is False and b_now.session_version == before + 1
    # a manager who still has reports
    response = await client.patch(f"{USERS}/{manager.id}", json={"active": False})
    assert response.status_code == 422 and (await fresh(db_session, User, manager.id)).active is True
    # reactivation is unchanged (LC4)
    assert (await client.patch(f"{USERS}/{b.id}", json={"active": True})).status_code == 200
    assert (await fresh(db_session, User, b.id)).active is True


@pytest.mark.asyncio
async def test_plain_patch_for_other_roles_is_unchanged(client, db_session):
    counselor = await make_counselor(db_session)
    before = counselor.session_version
    await as_user(client, await make_user(db_session, "super_admin", "global"))
    assert (await client.patch(f"{USERS}/{counselor.id}", json={"active": False})).status_code == 200
    now = await fresh(db_session, User, counselor.id)
    assert now.active is False and now.session_version == before
