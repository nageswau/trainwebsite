"""mgmt-001 -- partner + accountant roles: provisioning, sign-in, tiers, GET /management/me (spec §2 MG1-MG7; AC1, AC2, AC5)."""

import pytest
from sqlalchemy import select, update

from app.models import User
from app.services import management_access
from app.services.provisioning import _set_password_url
from tests.bdm001_helpers import PASSWORD, USERS, email, login, make_user
from tests.upc001_helpers import as_role

ME = "/api/v1/management/me"


def payload(role: str, **overrides) -> dict:
    body = {"role": role, "division": "global", "email": email(role), "full_name": f"Demo {role.title()}"}
    body.update(overrides)
    return body


# --- tiers (MG4) --------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("role", "operational", "finance", "partner_only"),
    [
        ("partner", True, True, True),
        ("accountant", False, True, False),
        ("super_admin", True, False, False),
        ("it_admin", False, False, False),
        ("overseas_admin", False, False, False),
        ("placement_manager", False, False, False),
    ],
)
def test_tier_truth_table(role, operational, finance, partner_only):
    user = User(role=role)
    assert management_access.can_view_operational(user) is operational
    assert management_access.can_view_finance(user) is finance
    assert management_access.can_view_partner_only(user) is partner_only


def test_require_partner_only_refuses_accountant_and_super_admin():
    from fastapi import HTTPException

    for role in ("accountant", "super_admin"):
        with pytest.raises(HTTPException) as exc:
            management_access.require_partner_only(User(role=role))
        assert exc.value.status_code == 403
    management_access.require_partner_only(User(role="partner"))


def test_rbac_bundles():
    from app.core.rbac import has_permission

    assert has_permission("partner", "management:finance") and has_permission("partner", "management:partner")
    assert has_permission("accountant", "management:finance") and not has_permission("accountant", "management:partner")


# --- AC1: super_admin creates two partners and an accountant; each sets a password and signs in at /admin -------------------
@pytest.mark.asyncio
async def test_super_admin_provisions_two_partners_and_an_accountant_who_sign_in(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    created = []
    for role in ("partner", "partner", "accountant"):
        response = await client.post(USERS, json=payload(role))
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["role"] == role and body["division"] == "global"
        created.append(body)
    for body in created:
        reset = await client.post("/api/v1/auth/reset-password", json={"token": body["development_welcome_token"], "new_password": PASSWORD})
        assert reset.status_code == 200, reset.text
        assert reset.json()["login_portal"] == "admin"
        signed_in = await client.post("/api/v1/auth/login", json={"email": body["email"], "password": PASSWORD, "division": "global"})
        assert signed_in.status_code == 200, signed_in.text
        me = await client.get(ME)
        assert me.status_code == 200 and me.json()["role"] == body["role"]


@pytest.mark.asyncio
async def test_set_password_link_opens_the_admin_portal(db_session):
    for role in ("partner", "accountant"):
        user = await make_user(db_session, role, "global")
        assert "/admin/reset-password" in _set_password_url(user, "t")


# --- AC2: only super_admin creates either role -------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["partner", "accountant"])
@pytest.mark.parametrize(("actor", "division"), [("it_admin", "it"), ("overseas_admin", "overseas")])
@pytest.mark.parametrize("send_division", [True, False])
async def test_division_admin_creating_a_management_role_is_403(client, db_session, target, actor, division, send_division):
    await as_role(client, db_session, actor, division)
    body = payload(target)
    if not send_division:
        body.pop("division")
    response = await client.post(USERS, json=body)
    assert response.status_code == 403, response.text
    assert await db_session.scalar(select(User.id).where(User.email == body["email"])) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["partner", "accountant"])
async def test_management_role_outside_global_is_422(client, db_session, target):
    await as_role(client, db_session, "super_admin", "global")
    response = await client.post(USERS, json=payload(target, division="it"))
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_management_roles_reach_no_admin_route(client, db_session):
    """MG1/MG2: neither role is an admin -- no /admin/* access, so neither can provision anyone."""
    for role in ("partner", "accountant"):
        await as_role(client, db_session, role, "global")
        assert (await client.post(USERS, json=payload("accountant"))).status_code == 403
        assert (await client.get("/api/v1/admin/users")).status_code == 403


# --- GET /management/me (MG5) ------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "tiers"),
    [
        ("partner", {"operational": True, "finance": True, "partner_only": True}),
        ("accountant", {"operational": False, "finance": True, "partner_only": False}),
        ("super_admin", {"operational": True, "finance": False, "partner_only": False}),
    ],
)
async def test_me_returns_role_and_tiers(client, db_session, role, tiers):
    actor = await as_role(client, db_session, role, "global")
    response = await client.get(ME)
    assert response.status_code == 200, response.text
    assert response.json() == {"id": str(actor.id), "full_name": actor.full_name, "role": role, "tiers": tiers}


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("it_admin", "it"), ("overseas_admin", "overseas"), ("bdm_manager", "global"), ("it_student", "it")])
async def test_me_refuses_roles_without_a_tier(client, db_session, role, division):
    await as_role(client, db_session, role, division)
    assert (await client.get(ME)).status_code == 403


@pytest.mark.asyncio
async def test_me_signed_out_is_401(client):
    client.cookies.clear()
    assert (await client.get(ME)).status_code == 401


# --- deactivation (MG6, MG7) ---------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_deactivated_partner_session_ends(client, db_session):
    partner = await make_user(db_session, "partner", "global")
    await make_user(db_session, "partner", "global")  # another active partner, so the deactivation is allowed
    await login(client, partner)
    assert (await client.get(ME)).status_code == 200
    admin = await make_user(db_session, "super_admin", "global")
    partner_cookies = dict(client.cookies)
    await login(client, admin)
    assert (await client.patch(f"{USERS}/{partner.id}", json={"active": False})).status_code == 200
    client.cookies.clear()
    for name, value in partner_cookies.items():
        client.cookies.set(name, value)
    assert (await client.get(ME)).status_code == 401
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401


@pytest.mark.asyncio
async def test_last_active_partner_cannot_be_deactivated(client, db_session):
    """MG6. The test DB is shared and never truncated: the other active partners are parked inactive for the test and restored."""
    others = list((await db_session.scalars(select(User.id).where(User.role == "partner", User.active.is_(True)))).all())
    await db_session.execute(update(User).where(User.id.in_(others)).values(active=False))
    await db_session.commit()
    try:
        last = await make_user(db_session, "partner", "global")
        await as_role(client, db_session, "super_admin", "global")
        refused = await client.patch(f"{USERS}/{last.id}", json={"active": False})
        assert refused.status_code == 422, refused.text
        assert refused.json()["detail"] == "At least one partner must stay active"
        assert await db_session.scalar(select(User.active).where(User.id == last.id)) is True
        # A second active partner makes the first one deactivatable.
        await make_user(db_session, "partner", "global")
        assert (await client.patch(f"{USERS}/{last.id}", json={"active": False})).status_code == 200
        # Editing a partner without deactivating, and deactivating an accountant, are unaffected.
        accountant = await make_user(db_session, "accountant", "global")
        assert (await client.patch(f"{USERS}/{accountant.id}", json={"active": False})).status_code == 200
    finally:
        await db_session.execute(update(User).where(User.id.in_(others)).values(active=True))
        await db_session.commit()


# --- AC5 spot check: the existing global roles are still created exactly as before ------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["bdm_manager", "telecaller_manager", "placement_manager", "partnership_head", "super_admin"])
async def test_existing_global_roles_unchanged(client, db_session, role):
    await as_role(client, db_session, "super_admin", "global")
    assert (await client.post(USERS, json=payload(role))).status_code == 201
