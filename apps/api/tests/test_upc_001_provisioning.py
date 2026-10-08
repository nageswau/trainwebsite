"""upc-001 -- POST /admin/users partnership branch (spec §5; AC1, AC2, N1, N2; PU7)."""

import logging

import pytest
from sqlalchemy import func, select

from app.core.security import verify_password
from app.models import AuditLog, PartnershipProfile, PasswordResetToken, User
from app.services.provisioning import _set_password_url
from tests.tel001_helpers import create_telecaller, make_tl_manager
from tests.upc001_helpers import PASSWORD, USERS, as_role, create_manager, emp, head_payload, make_head, make_user, pm_payload


@pytest.fixture(autouse=True)
def _loggers_enabled():
    """An earlier in-process migration test's fileConfig disables existing app.* loggers (see ENH-003's note)."""
    for name in ("app.partnership", "app.admin", "app.provisioning"):
        logging.getLogger(name).disabled = False


async def _by_email(db, address):
    return await db.scalar(select(User).where(User.email == address))


# --- AC1 ------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_super_admin_creates_a_head_without_a_profile_and_with_a_welcome_link(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    response = await client.post(USERS, json=head_payload())
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["role"] == "partnership_head" and body["division"] == "global" and body["partnership_profile"] is None
    head = await _by_email(db_session, body["email"])
    assert not verify_password(PASSWORD, head.password_hash)
    welcome = select(func.count()).select_from(PasswordResetToken).where(PasswordResetToken.user_id == head.id, PasswordResetToken.purpose == "welcome")
    assert await db_session.scalar(welcome) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("super_admin", "global"), ("overseas_admin", "overseas")])
async def test_authorized_admin_creates_a_manager_in_overseas(client, db_session, role, division):
    head = await make_head(db_session)
    await as_role(client, db_session, role, division)
    response = await create_manager(client, head.id)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["role"] == "partnership_manager" and body["division"] == "overseas"
    assert body["telecaller_profile"] is None and body["bdm_profile"] is None
    assert body["partnership_profile"]["reporting_head"] == {"id": str(head.id), "full_name": head.full_name, "active": True}
    user = await _by_email(db_session, body["email"])
    assert not verify_password(PASSWORD, user.password_hash)
    profile = await db_session.scalar(select(PartnershipProfile).where(PartnershipProfile.user_id == user.id))
    assert profile is not None and profile.reporting_head_user_id == head.id


@pytest.mark.asyncio
async def test_set_password_links_head_on_admin_manager_on_overseas(client, db_session):
    head = await make_head(db_session)
    manager = await make_user(db_session, "partnership_manager", "overseas")
    assert "/admin/reset-password" in _set_password_url(head, "t")
    assert "/overseas/reset-password" in _set_password_url(manager, "t")


@pytest.mark.asyncio
async def test_audit_row_carries_the_profile_snapshot(client, db_session):
    head = await make_head(db_session)
    await as_role(client, db_session, "super_admin", "global")
    body = (await create_manager(client, head.id)).json()
    row = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == body["id"], AuditLog.action == "user.create"))
    assert row.metadata_json["partnership_profile"]["reporting_head_user_id"] == str(head.id)


# --- AC2 / PU7 ------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("overseas_admin", "overseas"), ("it_admin", "it")])
async def test_only_super_admin_creates_a_head(client, db_session, role, division):
    await as_role(client, db_session, role, division)
    response = await client.post(USERS, json=head_payload())
    assert response.status_code == 403
    assert await db_session.scalar(select(func.count()).select_from(User).where(User.role == "partnership_head", User.email == head_payload()["email"])) == 0


@pytest.mark.asyncio
async def test_overseas_admin_creating_a_head_gets_the_named_message(client, db_session):
    await as_role(client, db_session, "overseas_admin", "overseas")
    response = await client.post(USERS, json=head_payload())
    assert response.status_code == 403 and response.json()["detail"] == "Only a Super Admin can create partnership heads"


@pytest.mark.asyncio
async def test_it_admin_cannot_create_a_manager(client, db_session):
    head = await make_head(db_session)
    await as_role(client, db_session, "it_admin", "it")
    payload = pm_payload(head.id)
    response = await client.post(USERS, json=payload)
    assert response.status_code == 403
    assert await _by_email(db_session, payload["email"]) is None


# --- validation -----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(("profile", "message"), [
    ("missing", "Partnership profile is required"),
    ({"reporting_head_user_id": "HEAD"}, "Employee ID is required"),
    ({"employee_id": "   ", "reporting_head_user_id": "HEAD"}, None),
    ({"employee_id": "E1"}, "Reporting head is required"),
    ({"employee_id": "E1", "reporting_head_user_id": "nope"}, "Reporting head: choose a head from the list"),
    ({"employee_id": "E1", "reporting_head_user_id": "HEAD", "territory": "x"}, "Unknown field: territory"),
])
async def test_invalid_profile_is_a_readable_422(client, db_session, profile, message):
    head = await make_head(db_session)
    await as_role(client, db_session, "super_admin", "global")
    payload = pm_payload(head.id)
    if profile == "missing":
        payload.pop("partnership_profile")
    else:
        payload["partnership_profile"] = {k: (str(head.id) if v == "HEAD" else v) for k, v in profile.items()}
    response = await client.post(USERS, json=payload)
    assert response.status_code == 422, response.text
    if message:
        assert response.json()["detail"] == message
    assert await _by_email(db_session, payload["email"]) is None


@pytest.mark.asyncio
async def test_division_other_than_overseas_is_422(client, db_session):
    head = await make_head(db_session)
    await as_role(client, db_session, "super_admin", "global")
    response = await create_manager(client, head.id, division="it")
    assert response.status_code == 422 and response.json()["detail"] == "Division must be overseas for a partnership manager"


@pytest.mark.asyncio
async def test_stray_profile_on_another_role_is_422(client, db_session):
    head = await make_head(db_session)
    await as_role(client, db_session, "super_admin", "global")
    response = await client.post(USERS, json={**head_payload(), "partnership_profile": {"employee_id": emp(), "reporting_head_user_id": str(head.id)}})
    assert response.status_code == 422 and response.json()["detail"] == "Only a partnership manager has a partnership profile"


# --- N1 / N2 / edge -------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["not_a_head", "inactive_head", "missing"])
async def test_reporting_head_must_be_an_active_partnership_head(client, db_session, kind):
    if kind == "not_a_head":
        target = (await make_tl_manager(db_session)).id
    elif kind == "inactive_head":
        target = (await make_head(db_session, active=False)).id
    else:
        target = "11111111-1111-1111-1111-111111111111"
    await as_role(client, db_session, "super_admin", "global")
    payload = pm_payload(target)
    response = await client.post(USERS, json=payload)
    assert response.status_code == 422 and response.json()["detail"] == "Reporting head must be an active partnership head"
    assert await _by_email(db_session, payload["email"]) is None


@pytest.mark.asyncio
async def test_duplicate_employee_id_in_any_case_is_409_and_nothing_is_written(client, db_session):
    head = await make_head(db_session)
    await as_role(client, db_session, "super_admin", "global")
    employee_id = emp()
    first = await create_manager(client, head.id, partnership_profile={"employee_id": employee_id, "reporting_head_user_id": str(head.id)})
    assert first.status_code == 201
    payload = pm_payload(head.id, partnership_profile={"employee_id": employee_id.lower(), "reporting_head_user_id": str(head.id)})
    second = await client.post(USERS, json=payload)
    assert second.status_code == 409 and second.json()["detail"] == "Employee ID already exists"
    assert await _by_email(db_session, payload["email"]) is None


@pytest.mark.asyncio
async def test_supplied_password_is_refused(client, db_session):
    head = await make_head(db_session)
    await as_role(client, db_session, "super_admin", "global")
    response = await create_manager(client, head.id, password="Known-Pass-1!")
    assert response.status_code == 422


# --- AC5: existing roles unaffected ---------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_existing_roles_carry_a_null_partnership_profile(client, db_session):
    manager = await make_tl_manager(db_session)
    await as_role(client, db_session, "super_admin", "global")
    tel = await create_telecaller(client, manager.id)
    assert tel.status_code == 201 and tel.json()["partnership_profile"] is None
    counselor = await client.post(USERS, json={"role": "counselor", "division": "overseas", "email": f"c-{emp().lower()}@example.local", "full_name": "C"})
    assert counselor.status_code == 201 and counselor.json()["partnership_profile"] is None
