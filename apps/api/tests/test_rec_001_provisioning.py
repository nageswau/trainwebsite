"""rec-001 -- POST/PATCH /admin/users recruiter + placement manager branches (spec §4; AC1, AC2, AC5, negatives, edge cases)."""

import logging
import uuid

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, PasswordResetToken, RecruiterProfile, User
from tests.rec001_helpers import USERS, as_role, create_recruiter, emp, make_pm, make_recruiter, make_user, profile_of, rec_payload


@pytest.fixture(autouse=True)
def _loggers_enabled():
    """An earlier in-process migration test's fileConfig disables existing app.* loggers (see ENH-003's note)."""
    for name in ("app.recruiter", "app.admin", "app.provisioning"):
        logging.getLogger(name).disabled = False


def _pm_payload():
    return {"role": "placement_manager", "division": "global", "email": f"pm-{emp().lower()}@example.local", "full_name": "Meera Placement Manager"}


async def _by_email(db, address):
    return await db.scalar(select(User).where(User.email == address))


# --- AC1 ------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_super_admin_creates_a_manager_with_a_welcome_link_on_the_admin_portal(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    response = await client.post(USERS, json=_pm_payload())
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["role"] == "placement_manager" and body["division"] == "global" and body["recruiter_profile"] is None
    manager = await _by_email(db_session, body["email"])
    assert await profile_of(db_session, manager.id) is None  # a manager has no profile
    welcome = select(func.count()).select_from(PasswordResetToken).where(PasswordResetToken.user_id == manager.id, PasswordResetToken.purpose == "welcome")
    assert await db_session.scalar(welcome) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("super_admin", "global"), ("it_admin", "it")])
async def test_authorized_admin_creates_a_recruiter_under_a_manager(client, db_session, role, division):
    manager = await make_pm(db_session)
    await as_role(client, db_session, role, division)
    payload = rec_payload(manager.id)
    response = await client.post(USERS, json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["role"] == "placement_team" and body["division"] == "it"
    assert body["recruiter_profile"] == {
        "employee_id": payload["recruiter_profile"]["employee_id"],
        "reporting_manager": {"id": str(manager.id), "full_name": manager.full_name, "active": True},
    }
    user = await _by_email(db_session, body["email"])
    profile = await profile_of(db_session, user.id)
    assert profile.reporting_manager_user_id == manager.id
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "user.create", AuditLog.entity_id == str(user.id)))
    assert audit.metadata_json["recruiter_profile"] == {"employee_id": payload["recruiter_profile"]["employee_id"], "reporting_manager_user_id": str(manager.id)}


@pytest.mark.asyncio
async def test_welcome_and_reset_links_for_a_placement_manager_open_the_admin_portal(client, db_session):
    from app.services.provisioning import ADMIN_PORTAL_ROLES

    assert "placement_manager" in ADMIN_PORTAL_ROLES and "placement_team" not in ADMIN_PORTAL_ROLES


# --- AC2 + division rules -------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_it_admin_cannot_create_a_placement_manager(client, db_session):
    await as_role(client, db_session, "it_admin", "it")
    payload = _pm_payload()
    response = await client.post(USERS, json=payload)
    assert response.status_code == 403
    assert response.json()["detail"] == "Only a Super Admin can create placement managers"
    assert await _by_email(db_session, payload["email"]) is None


@pytest.mark.asyncio
async def test_overseas_admin_cannot_create_a_recruiter(client, db_session):
    manager = await make_pm(db_session)
    await as_role(client, db_session, "overseas_admin", "overseas")
    payload = rec_payload(manager.id)
    assert (await client.post(USERS, json=payload)).status_code == 403
    assert await _by_email(db_session, payload["email"]) is None


@pytest.mark.asyncio
async def test_placement_manager_is_only_valid_in_the_global_division(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    response = await client.post(USERS, json={**_pm_payload(), "division": "it"})
    assert response.status_code == 422


# --- negatives ----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["not_a_manager", "inactive_manager", "unknown_id"])
async def test_reporting_manager_must_be_an_active_placement_manager(client, db_session, kind):
    if kind == "not_a_manager":
        manager_id = (await make_user(db_session, "telecaller_manager", "global")).id
    elif kind == "inactive_manager":
        manager_id = (await make_pm(db_session, active=False)).id
    else:
        manager_id = uuid.uuid4()
    await as_role(client, db_session, "super_admin", "global")
    payload = rec_payload(manager_id)
    response = await client.post(USERS, json=payload)
    assert response.status_code == 422
    assert response.json()["detail"] == "Reporting manager must be an active placement manager"
    assert await _by_email(db_session, payload["email"]) is None  # nothing half-written


@pytest.mark.asyncio
async def test_duplicate_employee_id_is_409_case_insensitive_and_writes_nothing(client, db_session):
    manager = await make_pm(db_session)
    await as_role(client, db_session, "super_admin", "global")
    first = rec_payload(manager.id)
    assert (await client.post(USERS, json=first)).status_code == 201
    second = rec_payload(manager.id)
    second["recruiter_profile"]["employee_id"] = first["recruiter_profile"]["employee_id"].lower()
    response = await client.post(USERS, json=second)
    assert response.status_code == 409 and response.json()["detail"] == "Employee ID already exists"
    assert await _by_email(db_session, second["email"]) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(("profile", "detail"), [
    ({"reporting_manager_user_id": None}, "Employee ID is required"),
    ({"employee_id": "E-1"}, "Reporting manager is required"),
    ({"employee_id": "E-1", "reporting_manager_user_id": "nope"}, "Reporting manager: choose a manager from the list"),
    ({"employee_id": "E-1", "reporting_manager_user_id": str(uuid.uuid4()), "team": "it"}, "Unknown field: team"),
    ("not-an-object", "recruiter_profile must be an object"),
])
async def test_an_invalid_profile_is_a_readable_422(client, db_session, profile, detail):
    await as_role(client, db_session, "super_admin", "global")
    response = await client.post(USERS, json={**rec_payload(uuid.uuid4()), "recruiter_profile": profile})
    assert response.status_code == 422
    assert response.json()["detail"] == detail


@pytest.mark.asyncio
async def test_a_recruiter_profile_on_another_role_is_refused(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    response = await client.post(USERS, json={**rec_payload(uuid.uuid4()), "role": "hr_team"})
    assert response.status_code == 422 and response.json()["detail"] == "Only a recruiter has a recruiter profile"


# --- edge case: the legacy generic Users form ---------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_recruiter_created_without_a_profile_gets_an_empty_one(client, db_session):
    await as_role(client, db_session, "it_admin", "it")
    payload = {"role": "placement_team", "email": f"legacy-{emp().lower()}@example.local", "full_name": "Legacy Recruiter"}
    response = await client.post(USERS, json=payload)
    assert response.status_code == 201, response.text
    assert response.json()["recruiter_profile"] == {"employee_id": None, "reporting_manager": None}
    user = await _by_email(db_session, payload["email"])
    profile = await profile_of(db_session, user.id)
    assert profile.employee_id is None and profile.reporting_manager_user_id is None


@pytest.mark.asyncio
async def test_hr_team_creation_is_unchanged(client, db_session):
    """AC6: no profile for hr_team."""
    await as_role(client, db_session, "it_admin", "it")
    payload = {"role": "hr_team", "email": f"hr-{emp().lower()}@example.local", "full_name": "HR Person"}
    response = await client.post(USERS, json=payload)
    assert response.status_code == 201 and response.json()["recruiter_profile"] is None
    user = await _by_email(db_session, payload["email"])
    assert await db_session.scalar(select(RecruiterProfile).where(RecruiterProfile.user_id == user.id)) is None


# --- PATCH /admin/users/{id} ----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_admin_sets_a_manager_and_employee_id_on_a_backfilled_recruiter(client, db_session):
    """AC5: "no manager until one is set"."""
    recruiter = await make_recruiter(db_session)
    manager = await make_pm(db_session)
    actor = await as_role(client, db_session, "it_admin", "it")
    employee_id = emp()
    response = await client.patch(f"{USERS}/{recruiter.id}", json={"recruiter_profile": {"employee_id": employee_id, "reporting_manager_user_id": str(manager.id)}})
    assert response.status_code == 200, response.text
    profile = await profile_of(db_session, recruiter.id)
    assert (profile.employee_id, profile.reporting_manager_user_id) == (employee_id, manager.id)
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "user.update", AuditLog.entity_id == str(recruiter.id), AuditLog.user_id == actor.id))
    assert audit.metadata_json["recruiter_profile_before"] == {"employee_id": None, "reporting_manager_user_id": None}
    assert audit.metadata_json["recruiter_profile_after"] == {"employee_id": employee_id, "reporting_manager_user_id": str(manager.id)}


@pytest.mark.asyncio
async def test_unchanged_manager_is_not_rechecked_but_a_new_inactive_one_is_refused(client, db_session):
    manager = await make_pm(db_session)
    recruiter = await make_recruiter(db_session, manager, employee_id=emp())
    manager.active = False
    await db_session.commit()
    inactive = await make_pm(db_session, active=False)
    await as_role(client, db_session, "super_admin", "global")
    same = await client.patch(f"{USERS}/{recruiter.id}", json={"full_name": "Renamed", "recruiter_profile": {"reporting_manager_user_id": str(manager.id)}})
    assert same.status_code == 200, same.text
    moved = await client.patch(f"{USERS}/{recruiter.id}", json={"recruiter_profile": {"reporting_manager_user_id": str(inactive.id)}})
    assert moved.status_code == 422


@pytest.mark.asyncio
async def test_update_refuses_null_duplicates_and_a_profile_on_another_role(client, db_session):
    taken = emp()
    await make_recruiter(db_session, employee_id=taken)
    recruiter = await make_recruiter(db_session, employee_id=emp())
    hr = await make_user(db_session, "hr_team", "it")
    await as_role(client, db_session, "super_admin", "global")
    assert (await client.patch(f"{USERS}/{recruiter.id}", json={"recruiter_profile": {"employee_id": None}})).status_code == 422
    duplicate = await client.patch(f"{USERS}/{recruiter.id}", json={"recruiter_profile": {"employee_id": taken.upper()}})
    assert duplicate.status_code == 409
    other = await client.patch(f"{USERS}/{hr.id}", json={"recruiter_profile": {"employee_id": emp()}})
    assert other.status_code == 422 and other.json()["detail"] == "Only a recruiter has a recruiter profile"


@pytest.mark.asyncio
async def test_update_creates_a_missing_profile_for_a_recruiter(client, db_session):
    recruiter = await make_user(db_session, "placement_team", "it")  # a row written outside the API
    manager = await make_pm(db_session)
    await as_role(client, db_session, "super_admin", "global")
    response = await client.patch(f"{USERS}/{recruiter.id}", json={"recruiter_profile": {"employee_id": emp(), "reporting_manager_user_id": str(manager.id)}})
    assert response.status_code == 200, response.text
    assert (await profile_of(db_session, recruiter.id)).reporting_manager_user_id == manager.id
