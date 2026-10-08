"""upc-001 -- PATCH /admin/users/{id} partnership branch (spec §5; N1, N2, PU10)."""

import pytest
from sqlalchemy import select

from app.models import AuditLog, PartnershipProfile
from tests.tel001_helpers import make_tl_manager
from tests.upc001_helpers import USERS, as_role, create_manager, emp, make_head, make_user


async def _created(client, db, head):
    await as_role(client, db, "super_admin", "global")
    body = (await create_manager(client, head.id)).json()
    return body


@pytest.mark.asyncio
async def test_admin_changes_employee_id_and_head_with_an_audit_before_after(client, db_session):
    head, other = await make_head(db_session), await make_head(db_session)
    body = await _created(client, db_session, head)
    new_emp = emp()
    response = await client.patch(f"{USERS}/{body['id']}", json={"partnership_profile": {"employee_id": new_emp, "reporting_head_user_id": str(other.id)}})
    assert response.status_code == 200, response.text
    profile = await db_session.scalar(select(PartnershipProfile).where(PartnershipProfile.user_id == body["id"]).execution_options(populate_existing=True))
    assert profile.employee_id == new_emp and profile.reporting_head_user_id == other.id
    row = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == body["id"], AuditLog.action == "user.update"))
    assert row.metadata_json["partnership_profile_before"]["reporting_head_user_id"] == str(head.id)
    assert row.metadata_json["partnership_profile_after"]["reporting_head_user_id"] == str(other.id)


@pytest.mark.asyncio
async def test_overseas_admin_edits_a_manager(client, db_session):
    head = await make_head(db_session)
    body = await _created(client, db_session, head)
    await as_role(client, db_session, "overseas_admin", "overseas")
    response = await client.patch(f"{USERS}/{body['id']}", json={"full_name": "Rahul R", "partnership_profile": {"employee_id": emp()}})
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["not_a_head", "inactive_head"])
async def test_new_head_must_be_active_partnership_head(client, db_session, kind):
    head = await make_head(db_session)
    body = await _created(client, db_session, head)
    target = await make_tl_manager(db_session) if kind == "not_a_head" else await make_head(db_session, active=False)
    response = await client.patch(f"{USERS}/{body['id']}", json={"partnership_profile": {"reporting_head_user_id": str(target.id)}})
    assert response.status_code == 422 and response.json()["detail"] == "Reporting head must be an active partnership head"


@pytest.mark.asyncio
async def test_unchanged_head_that_is_now_inactive_stays_editable(client, db_session):
    head = await make_head(db_session)
    body = await _created(client, db_session, head)
    head.active = False
    await db_session.commit()
    response = await client.patch(f"{USERS}/{body['id']}", json={"partnership_profile": {"employee_id": emp(), "reporting_head_user_id": str(head.id)}})
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_duplicate_employee_id_on_edit_is_409(client, db_session):
    head = await make_head(db_session)
    await as_role(client, db_session, "super_admin", "global")
    first = (await create_manager(client, head.id)).json()
    second = (await create_manager(client, head.id)).json()
    response = await client.patch(f"{USERS}/{second['id']}", json={"partnership_profile": {"employee_id": first["partnership_profile"]["employee_id"].upper()}})
    assert response.status_code == 409 and response.json()["detail"] == "Employee ID already exists"


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["employee_id", "reporting_head_user_id"])
async def test_explicit_null_is_422(client, db_session, field):
    head = await make_head(db_session)
    body = await _created(client, db_session, head)
    response = await client.patch(f"{USERS}/{body['id']}", json={"partnership_profile": {field: None}})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_profile_on_a_non_manager_is_422(client, db_session):
    head = await make_head(db_session)
    other = await make_user(db_session, "counselor", "overseas")
    await as_role(client, db_session, "super_admin", "global")
    response = await client.patch(f"{USERS}/{other.id}", json={"partnership_profile": {"employee_id": emp(), "reporting_head_user_id": str(head.id)}})
    assert response.status_code == 422 and response.json()["detail"] == "Only a partnership manager has a partnership profile"


@pytest.mark.asyncio
async def test_overseas_admin_cannot_edit_or_deactivate_a_head(client, db_session):
    head = await make_head(db_session)
    await as_role(client, db_session, "overseas_admin", "overseas")
    response = await client.patch(f"{USERS}/{head.id}", json={"active": False})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_plain_deactivation_of_a_manager_works(client, db_session):
    head = await make_head(db_session)
    body = await _created(client, db_session, head)
    response = await client.patch(f"{USERS}/{body['id']}", json={"active": False})
    assert response.status_code == 200, response.text
