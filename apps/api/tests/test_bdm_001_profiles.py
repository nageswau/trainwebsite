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
