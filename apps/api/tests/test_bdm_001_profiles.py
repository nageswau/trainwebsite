"""bdm-001 -- POST/PATCH /admin/users BDM branches (spec §5.4, §5.5; AC01-AC04, AC07-AC09, AC14-AC16)."""

import asyncio
import logging
import uuid

import pytest
from sqlalchemy import func, select

from app.core.security import verify_password
from app.models import AuditLog, BdmProfile, PasswordResetToken, User
from tests.bdm001_helpers import PASSWORD, USERS, bdm_payload, create_bdm, emp, login, make_manager, make_user


@pytest.fixture(autouse=True)
def _loggers_enabled():
    """Alembic's fileConfig in an earlier in-process migration test disables existing app.* loggers (see ENH-003's note)."""
    for name in ("app.bdm", "app.admin", "app.provisioning"):
        logging.getLogger(name).disabled = False


async def _super(client, db):
    admin = await make_user(db, "super_admin", "global")
    await login(client, admin)
    return admin


async def _user_by_email(db, address):
    return await db.scalar(select(User).where(User.email == address))


# --- AC01 / AC08: who may create what -------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "division", "bdm_type", "expected_division"),
    [("super_admin", "global", "agent", "overseas"), ("it_admin", "it", "college", "it"), ("overseas_admin", "overseas", "school", "overseas"), ("overseas_admin", "overseas", "agent", "overseas")],
)
async def test_authorized_admin_creates_a_bdm_with_a_link_and_no_password(client, db_session, role, division, bdm_type, expected_division):
    manager = await make_manager(db_session)
    await login(client, await make_user(db_session, role, division))
    response = await create_bdm(client, manager.id, bdm_type=bdm_type)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["role"] == "bdm" and body["division"] == expected_division
    assert body["bdm_profile"]["bdm_type"] == bdm_type
    assert body["bdm_profile"]["reporting_manager"] == {"id": str(manager.id), "full_name": manager.full_name, "active": True}
    assert not any("password" in key.lower() for key in body)
    user = await _user_by_email(db_session, body["email"])
    assert not verify_password(PASSWORD, user.password_hash)
    welcome = select(func.count()).select_from(PasswordResetToken).where(PasswordResetToken.user_id == user.id, PasswordResetToken.purpose == "welcome")
    assert await db_session.scalar(welcome) == 1
    assert await db_session.scalar(select(BdmProfile).where(BdmProfile.user_id == user.id)) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division", "bdm_type"), [("it_admin", "it", "agent"), ("it_admin", "it", "school"), ("overseas_admin", "overseas", "college")])
async def test_admin_outside_its_types_gets_403_and_nothing_is_written(client, db_session, role, division, bdm_type):
    manager = await make_manager(db_session)
    await login(client, await make_user(db_session, role, division))
    payload = bdm_payload(manager.id, bdm_type=bdm_type)
    assert (await client.post(USERS, json=payload)).status_code == 403
    assert await _user_by_email(db_session, payload["email"]) is None


@pytest.mark.asyncio
async def test_only_super_admin_creates_a_manager(client, db_session):
    payload = lambda: {"role": "bdm_manager", "division": "global", "email": f"m-{emp().lower()}@example.local", "full_name": "M"}  # noqa: E731
    await login(client, await make_user(db_session, "it_admin", "it"))
    assert (await client.post(USERS, json=payload())).status_code == 403
    await _super(client, db_session)
    response = await client.post(USERS, json=payload())
    assert response.status_code == 201
    assert response.json()["bdm_profile"] is None and response.json()["division"] == "global"


@pytest.mark.asyncio
async def test_supplied_password_is_422(client, db_session):
    manager = await make_manager(db_session)
    await _super(client, db_session)
    assert (await create_bdm(client, manager.id, password="Whatever-123!")).status_code == 422


# --- AC02: division -------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(("bdm_type", "division"), [("college", "overseas"), ("agent", "it"), ("school", "global")])
async def test_mismatched_division_is_422(client, db_session, bdm_type, division):
    manager = await make_manager(db_session)
    await _super(client, db_session)
    response = await create_bdm(client, manager.id, bdm_type=bdm_type, division=division)
    assert response.status_code == 422
    assert response.json()["detail"].startswith("Division must be")


@pytest.mark.asyncio
async def test_matching_explicit_division_is_accepted(client, db_session):
    manager = await make_manager(db_session)
    await _super(client, db_session)
    assert (await create_bdm(client, manager.id, bdm_type="school", division="overseas")).status_code == 201


# --- AC03: Employee ID ----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_employee_id_trimmed_and_case_insensitive(client, db_session):
    manager = await make_manager(db_session)
    await _super(client, db_session)
    code = emp()
    first = bdm_payload(manager.id)
    first["bdm_profile"]["employee_id"] = f"  {code} "
    assert (await client.post(USERS, json=first)).json()["bdm_profile"]["employee_id"] == code
    dup = bdm_payload(manager.id)
    dup["bdm_profile"]["employee_id"] = code.lower()
    before = await db_session.scalar(select(func.count()).select_from(User))
    response = await client.post(USERS, json=dup)
    assert response.status_code == 409 and response.json()["detail"] == "Employee ID already exists"
    assert await db_session.scalar(select(func.count()).select_from(User)) == before


@pytest.mark.asyncio
async def test_concurrent_duplicate_employee_id_is_one_201_one_409(client, db_session):
    manager = await make_manager(db_session)
    await _super(client, db_session)
    a, b = bdm_payload(manager.id), bdm_payload(manager.id)
    b["bdm_profile"]["employee_id"] = a["bdm_profile"]["employee_id"]
    results = await asyncio.gather(client.post(USERS, json=a), client.post(USERS, json=b))
    assert sorted(r.status_code for r in results) == [201, 409]


# --- AC04: reporting manager ----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["missing", "inactive", "counselor", "bdm_user"])
async def test_invalid_manager_is_422(client, db_session, kind):
    await _super(client, db_session)
    if kind == "missing":
        target = uuid.uuid4()
    elif kind == "inactive":
        target = (await make_manager(db_session, active=False)).id
    elif kind == "counselor":
        target = (await make_user(db_session, "counselor", "overseas")).id
    else:
        target = (await make_user(db_session, "bdm", "it")).id
    payload = bdm_payload(target)
    response = await client.post(USERS, json=payload)
    assert response.status_code == 422
    assert response.json()["detail"] == "Reporting manager must be an active BDM manager"
    assert await _user_by_email(db_session, payload["email"]) is None


# --- AC09 / AC15 / AC16: shapes and malformed input -----------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("profile", [None, "x", [], 5])
async def test_profile_not_an_object_is_422(client, db_session, profile):
    manager = await make_manager(db_session)
    await _super(client, db_session)
    assert (await create_bdm(client, manager.id, bdm_profile=profile)).status_code == 422


@pytest.mark.asyncio
async def test_bdm_without_profile_is_422_and_profile_on_other_role_is_422(client, db_session):
    manager = await make_manager(db_session)
    await _super(client, db_session)
    payload = bdm_payload(manager.id)
    del payload["bdm_profile"]
    assert (await client.post(USERS, json=payload)).status_code == 422
    other = bdm_payload(manager.id, role="counselor", division="overseas")
    assert (await client.post(USERS, json=other)).status_code == 422
    assert await _user_by_email(db_session, other["email"]) is None


@pytest.mark.asyncio
async def test_non_bdm_create_has_null_bdm_profile_and_is_otherwise_unchanged(client, db_session):
    await _super(client, db_session)
    response = await client.post(USERS, json={"role": "counselor", "division": "overseas", "email": f"c-{emp().lower()}@example.local", "full_name": "C"})
    assert response.status_code == 201
    assert {"id", "email", "role", "division", "email_status", "bdm_profile"} <= set(response.json())
    assert response.json()["bdm_profile"] is None


# --- AC07: audit ----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_writes_one_audit_row_with_the_profile(client, db_session):
    manager = await make_manager(db_session)
    admin = await _super(client, db_session)
    body = (await create_bdm(client, manager.id)).json()
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "user.create", AuditLog.entity_id == str(body["id"])))).all()
    assert len(rows) == 1 and rows[0].user_id == admin.id
    meta = rows[0].metadata_json
    assert meta["role"] == "bdm"
    assert meta["bdm_profile"]["employee_id"] == body["bdm_profile"]["employee_id"]
    assert meta["bdm_profile"]["reporting_manager_user_id"] == str(manager.id)


# --- PATCH /admin/users/{id} (spec §5.5) ----------------------------------------------------------------------------------
async def _bdm(client, db_session, **overrides):
    manager = await make_manager(db_session)
    await _super(client, db_session)
    body = (await create_bdm(client, manager.id, **overrides)).json()
    return body, manager


def _patch(client, user_id, payload):
    return client.patch(f"{USERS}/{user_id}", json=payload)


async def _profile(db_session, user_id):
    db_session.expire_all()
    return await db_session.scalar(select(BdmProfile).where(BdmProfile.user_id == uuid.UUID(str(user_id))))


async def _update_audits(db_session, user_id):
    return (await db_session.scalars(select(AuditLog).where(AuditLog.action == "user.update", AuditLog.entity_id == str(user_id)))).all()


@pytest.mark.asyncio
async def test_patch_profile_fields_and_audit_before_after(client, db_session):
    body, _ = await _bdm(client, db_session)
    other_id = (await make_manager(db_session)).id  # read before _profile() expires the session's objects
    response = await _patch(client, body["id"], {"bdm_profile": {"territory": "Kollam", "designation": None, "reporting_manager_user_id": str(other_id)}})
    assert response.status_code == 200 and response.json() == {"ok": True}
    profile = await _profile(db_session, body["id"])
    assert (profile.territory, profile.designation, profile.reporting_manager_user_id) == ("Kollam", None, other_id)
    meta = (await _update_audits(db_session, body["id"]))[-1].metadata_json
    assert meta["bdm_profile_before"]["territory"] == "Kochi" and meta["bdm_profile_after"]["territory"] == "Kollam"
    assert meta["bdm_profile_after"]["reporting_manager_user_id"] == str(other_id)


@pytest.mark.asyncio
async def test_patch_user_fields_only_is_audited_without_profile_snapshots(client, db_session):
    body, _ = await _bdm(client, db_session)
    assert (await _patch(client, body["id"], {"full_name": "Renamed"})).status_code == 200
    meta = (await _update_audits(db_session, body["id"]))[-1].metadata_json
    assert meta == {"full_name": "Renamed"}


@pytest.mark.asyncio
async def test_patch_type_change_is_422_and_same_type_is_a_noop(client, db_session):
    body, _ = await _bdm(client, db_session)
    response = await _patch(client, body["id"], {"bdm_profile": {"bdm_type": "agent"}})
    assert response.status_code == 422 and response.json()["detail"] == "BDM type cannot be changed"
    assert (await _patch(client, body["id"], {"bdm_profile": {"bdm_type": "college"}})).status_code == 200
    assert (await _profile(db_session, body["id"])).bdm_type == "college"


@pytest.mark.asyncio
async def test_patch_duplicate_employee_id_is_409_and_nothing_changes(client, db_session):
    first, _ = await _bdm(client, db_session)
    second, _ = await _bdm(client, db_session)
    response = await _patch(client, second["id"], {"full_name": "Changed", "bdm_profile": {"employee_id": first["bdm_profile"]["employee_id"].upper()}})
    assert response.status_code == 409
    db_session.expire_all()
    assert (await db_session.get(User, uuid.UUID(second["id"]))).full_name == "Asha BDM"
    assert (await _profile(db_session, second["id"])).employee_id == second["bdm_profile"]["employee_id"]


@pytest.mark.asyncio
async def test_patch_invalid_manager_is_422(client, db_session):
    body, _ = await _bdm(client, db_session)
    inactive = await make_manager(db_session, active=False)
    response = await _patch(client, body["id"], {"bdm_profile": {"reporting_manager_user_id": str(inactive.id)}})
    assert response.status_code == 422 and response.json()["detail"] == "Reporting manager must be an active BDM manager"


@pytest.mark.asyncio
async def test_patch_other_fields_when_manager_inactive_succeeds(client, db_session):
    body, manager = await _bdm(client, db_session)
    assert (await _patch(client, manager.id, {"active": False})).status_code == 200
    payload = {"bdm_profile": {"territory": "Thrissur", "reporting_manager_user_id": str(manager.id)}}
    assert (await _patch(client, body["id"], payload)).status_code == 200
    assert (await _profile(db_session, body["id"])).territory == "Thrissur"


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", [{"employee_id": None}, {"reporting_manager_user_id": None}, {"user_id": "x"}, "x", None])
async def test_patch_bad_profile_is_422(client, db_session, profile):
    body, _ = await _bdm(client, db_session)
    assert (await _patch(client, body["id"], {"bdm_profile": profile})).status_code == 422


@pytest.mark.asyncio
async def test_patch_profile_on_non_bdm_is_422(client, db_session):
    await _super(client, db_session)
    target = await make_user(db_session, "counselor", "overseas")
    response = await _patch(client, target.id, {"bdm_profile": {"territory": "X"}})
    assert response.status_code == 422 and response.json()["detail"] == "Only a BDM has a BDM profile"


@pytest.mark.asyncio
async def test_patch_ignores_role_and_division_escalation(client, db_session):
    body, _ = await _bdm(client, db_session)
    assert (await _patch(client, body["id"], {"role": "super_admin", "division": "global"})).status_code == 200
    db_session.expire_all()
    user = await db_session.get(User, uuid.UUID(body["id"]))
    assert (user.role, user.division) == ("bdm", "it")


@pytest.mark.asyncio
async def test_division_admin_patches_only_types_it_manages(client, db_session):
    agent_bdm, _ = await _bdm(client, db_session, bdm_type="agent")
    college_bdm, _ = await _bdm(client, db_session)
    await login(client, await make_user(db_session, "overseas_admin", "overseas"))
    assert (await _patch(client, agent_bdm["id"], {"bdm_profile": {"territory": "Ok"}})).status_code == 200
    await login(client, await make_user(db_session, "it_admin", "it"))
    assert (await _patch(client, agent_bdm["id"], {"bdm_profile": {"territory": "X"}})).status_code == 403
    assert (await _patch(client, college_bdm["id"], {"bdm_profile": {"territory": "Ok"}})).status_code == 200


@pytest.mark.asyncio
async def test_concurrent_patches_both_audited_and_chain(client, db_session):
    body, _ = await _bdm(client, db_session)
    results = await asyncio.gather(_patch(client, body["id"], {"bdm_profile": {"territory": "A"}}), _patch(client, body["id"], {"bdm_profile": {"territory": "B"}}))
    assert [r.status_code for r in results] == [200, 200]
    first, second = [row.metadata_json for row in (await _update_audits(db_session, body["id"]))[-2:]]
    # The profile row lock serialises the writes, so one's "before" is exactly the other's "after" (whichever order ran); without
    # the lock both would read "Kochi" as their before. created_at is now() = transaction start, so row order is not run order.
    assert first["bdm_profile_before"]["territory"] == second["bdm_profile_after"]["territory"] or second["bdm_profile_before"]["territory"] == first["bdm_profile_after"]["territory"]
