"""tel-001 -- POST /admin/users telecaller branch (spec §5.4, §5.6; AC1, AC2)."""

import hashlib
import logging
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.core.security import verify_password
from app.models import AuditLog, PasswordResetToken, TelecallerProfile, User
from tests.bdm001_helpers import bdm_payload, make_manager
from tests.tel001_helpers import PASSWORD, USERS, create_telecaller, emp, login, make_tl_manager, make_user, tel_payload


@pytest.fixture(autouse=True)
def _loggers_enabled():
    """An earlier in-process migration test's fileConfig disables existing app.* loggers (see ENH-003's note)."""
    for name in ("app.telecaller", "app.admin", "app.provisioning"):
        logging.getLogger(name).disabled = False


async def _as(client, db, role: str, division: str):
    actor = await make_user(db, role, division)
    await login(client, actor)
    return actor


async def _by_email(db, address):
    return await db.scalar(select(User).where(User.email == address))


def _manager_payload():
    return {"role": "telecaller_manager", "division": "global", "email": f"tm-{emp().lower()}@example.local", "full_name": "Meena Manager"}


# --- AC1 ------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division", "team"), [("super_admin", "global", "it"), ("super_admin", "global", "overseas"), ("it_admin", "it", "it"), ("overseas_admin", "overseas", "overseas")])
async def test_authorized_admin_creates_a_telecaller_with_a_link_and_no_password(client, db_session, role, division, team):
    manager = await make_tl_manager(db_session)
    await _as(client, db_session, role, division)
    response = await create_telecaller(client, manager.id, team=team)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["role"] == "telecaller" and body["division"] == team and body["bdm_profile"] is None
    assert body["telecaller_profile"]["team"] == team
    assert body["telecaller_profile"]["reporting_manager"] == {"id": str(manager.id), "full_name": manager.full_name, "active": True}
    assert not any("password" in key.lower() for key in body)
    user = await _by_email(db_session, body["email"])
    assert not verify_password(PASSWORD, user.password_hash)
    welcome = select(func.count()).select_from(PasswordResetToken).where(PasswordResetToken.user_id == user.id, PasswordResetToken.purpose == "welcome")
    assert await db_session.scalar(welcome) == 1
    assert await db_session.scalar(select(TelecallerProfile).where(TelecallerProfile.user_id == user.id)) is not None


@pytest.mark.asyncio
async def test_super_admin_creates_a_manager_without_a_profile(client, db_session):
    await _as(client, db_session, "super_admin", "global")
    response = await client.post(USERS, json=_manager_payload())
    assert response.status_code == 201, response.text
    assert response.json()["division"] == "global" and response.json()["telecaller_profile"] is None


@pytest.mark.asyncio
async def test_audit_row_carries_the_profile_snapshot(client, db_session):
    manager = await make_tl_manager(db_session)
    await _as(client, db_session, "super_admin", "global")
    body = (await create_telecaller(client, manager.id)).json()
    row = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == body["id"], AuditLog.action == "user.create"))
    assert row.metadata_json["telecaller_profile"]["team"] == "it"
    assert row.metadata_json["telecaller_profile"]["reporting_manager_user_id"] == str(manager.id)


# --- AC2 ------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division", "team"), [("it_admin", "it", "overseas"), ("overseas_admin", "overseas", "it")])
async def test_division_admin_cannot_create_the_other_team(client, db_session, role, division, team):
    manager = await make_tl_manager(db_session)
    await _as(client, db_session, role, division)
    payload = tel_payload(manager.id, team=team)
    response = await client.post(USERS, json=payload)
    assert response.status_code == 403
    assert response.json()["detail"] == f"Your role cannot manage {'Overseas' if team == 'overseas' else 'IT'} telecallers"
    assert await _by_email(db_session, payload["email"]) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("it_admin", "it"), ("overseas_admin", "overseas")])
async def test_only_super_admin_creates_a_manager(client, db_session, role, division):
    await _as(client, db_session, role, division)
    response = await client.post(USERS, json=_manager_payload())
    assert response.status_code == 403 and response.json()["detail"] == "Only a Super Admin can create telecaller managers"


# --- validation and conflicts -----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_missing_profile_and_mismatched_division_are_422(client, db_session):
    manager = await make_tl_manager(db_session)
    await _as(client, db_session, "super_admin", "global")
    missing = tel_payload(manager.id)
    del missing["telecaller_profile"]
    response = await client.post(USERS, json=missing)
    assert response.status_code == 422 and response.json()["detail"] == "Telecaller profile is required"
    response = await create_telecaller(client, manager.id, team="it", division="overseas")
    assert response.status_code == 422 and response.json()["detail"] == "Division must match the telecaller's team"


@pytest.mark.asyncio
async def test_profiles_cannot_cross_roles(client, db_session):
    tl_manager, bdm_manager = await make_tl_manager(db_session), await make_manager(db_session)
    await _as(client, db_session, "super_admin", "global")
    stray_tel = bdm_payload(bdm_manager.id, telecaller_profile={"team": "it", "employee_id": emp(), "reporting_manager_user_id": str(tl_manager.id)})
    response = await client.post(USERS, json=stray_tel)
    assert response.status_code == 422 and response.json()["detail"] == "Only a telecaller has a telecaller profile"
    assert await _by_email(db_session, stray_tel["email"]) is None
    stray_bdm = tel_payload(tl_manager.id, bdm_profile={"bdm_type": "college", "employee_id": emp(), "reporting_manager_user_id": str(bdm_manager.id)})
    assert (await client.post(USERS, json=stray_bdm)).status_code == 422
    counselor = {"role": "counselor", "division": "overseas", "email": f"c-{emp().lower()}@example.local", "full_name": "C", "telecaller_profile": {}}
    assert (await client.post(USERS, json=counselor)).status_code == 422


@pytest.mark.asyncio
async def test_reporting_manager_must_be_an_active_telecaller_manager(client, db_session):
    inactive, bdm_manager = await make_tl_manager(db_session, active=False), await make_manager(db_session)
    await _as(client, db_session, "super_admin", "global")
    for bad in (inactive.id, bdm_manager.id, uuid.uuid4()):
        payload = tel_payload(bad)
        response = await client.post(USERS, json=payload)
        assert response.status_code == 422 and response.json()["detail"] == "Reporting manager must be an active telecaller manager"
        assert await _by_email(db_session, payload["email"]) is None


@pytest.mark.asyncio
async def test_duplicate_employee_id_is_409_case_and_space_insensitive(client, db_session):
    manager = await make_tl_manager(db_session)
    await _as(client, db_session, "super_admin", "global")
    first = tel_payload(manager.id)
    assert (await client.post(USERS, json=first)).status_code == 201
    again = tel_payload(manager.id)
    again["telecaller_profile"]["employee_id"] = f"  {first['telecaller_profile']['employee_id'].lower()} "
    response = await client.post(USERS, json=again)
    assert response.status_code == 409 and response.json()["detail"] == "Employee ID already exists"
    assert await _by_email(db_session, again["email"]) is None


@pytest.mark.asyncio
async def test_supplied_password_is_422(client, db_session):
    manager = await make_tl_manager(db_session)
    await _as(client, db_session, "super_admin", "global")
    assert (await create_telecaller(client, manager.id, password="Whatever-123!")).status_code == 422


# --- set-password link and reset routing (spec §5.6) ------------------------------------------------------------------------
async def _token(db, user, purpose: str = "welcome") -> str:
    raw = uuid.uuid4().hex * 2
    db.add(PasswordResetToken(user_id=user.id, token_hash=hashlib.sha256(raw.encode()).hexdigest(), purpose=purpose, expires_at=datetime.now(UTC) + timedelta(hours=72)))
    await db.commit()
    return raw


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division", "portal"), [("telecaller_manager", "global", "admin"), ("telecaller", "it", None), ("telecaller", "overseas", None)])
async def test_reset_names_the_admin_portal_only_for_a_telecaller_manager(client, db_session, role, division, portal):
    user = await make_user(db_session, role, division)
    response = await client.post("/api/v1/auth/reset-password", json={"token": await _token(db_session, user), "new_password": "Brand-New-Pass-1!"})
    assert response.json() == {"ok": True, "login_portal": portal}
