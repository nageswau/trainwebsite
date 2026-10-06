"""tel-001 -- PATCH /admin/users/{id} telecaller branch (spec §5.5; TL7)."""

import pytest
from sqlalchemy import select

from app.models import AuditLog, TelecallerProfile
from tests.tel001_helpers import create_telecaller, emp, login, make_tl_manager, make_user

USER = "/api/v1/admin/users/{}"


async def _created(client, db, *, team: str = "it"):
    m1, m2 = await make_tl_manager(db), await make_tl_manager(db)
    await login(client, await make_user(db, "super_admin", "global"))
    body = (await create_telecaller(client, m1.id, team=team)).json()
    return m1, m2, body


async def _profile(db, user_id):
    db.expire_all()
    return await db.scalar(select(TelecallerProfile).where(TelecallerProfile.user_id == user_id))


@pytest.mark.asyncio
async def test_admin_changes_employee_id_and_manager_with_an_audit_trail(client, db_session):
    m1, m2, body = await _created(client, db_session)
    m1_id, m2_id = m1.id, m2.id  # read before _profile() expires the session
    new_emp = emp()
    response = await client.patch(USER.format(body["id"]), json={"telecaller_profile": {"employee_id": new_emp, "reporting_manager_user_id": str(m2_id)}})
    assert response.status_code == 200, response.text
    profile = await _profile(db_session, body["id"])
    assert profile.employee_id == new_emp and profile.reporting_manager_user_id == m2_id
    row = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == body["id"], AuditLog.action == "user.update"))
    assert row.metadata_json["telecaller_profile_before"]["reporting_manager_user_id"] == str(m1_id)
    assert row.metadata_json["telecaller_profile_after"]["reporting_manager_user_id"] == str(m2_id)


@pytest.mark.asyncio
async def test_team_cannot_change_but_an_equal_team_is_a_no_op(client, db_session):
    _, _, body = await _created(client, db_session)
    response = await client.patch(USER.format(body["id"]), json={"telecaller_profile": {"team": "overseas"}})
    assert response.status_code == 422 and response.json()["detail"] == "Team cannot be changed here"
    assert (await client.patch(USER.format(body["id"]), json={"telecaller_profile": {"team": "it"}})).status_code == 200


@pytest.mark.asyncio
async def test_inactive_or_wrong_manager_and_null_required_fields_are_422(client, db_session):
    _, _, body = await _created(client, db_session)
    inactive = await make_tl_manager(db_session, active=False)
    response = await client.patch(USER.format(body["id"]), json={"telecaller_profile": {"reporting_manager_user_id": str(inactive.id)}})
    assert response.status_code == 422 and response.json()["detail"] == "Reporting manager must be an active telecaller manager"
    response = await client.patch(USER.format(body["id"]), json={"telecaller_profile": {"employee_id": None}})
    assert response.status_code == 422 and response.json()["detail"] == "Employee ID is required"


@pytest.mark.asyncio
async def test_duplicate_employee_id_on_edit_is_409(client, db_session):
    m1, _, body = await _created(client, db_session)
    other = (await create_telecaller(client, m1.id)).json()
    response = await client.patch(USER.format(body["id"]), json={"telecaller_profile": {"employee_id": other["telecaller_profile"]["employee_id"].upper()}})
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_profile_on_a_non_telecaller_is_422(client, db_session):
    await login(client, await make_user(db_session, "super_admin", "global"))
    counselor = await make_user(db_session, "counselor", "overseas")
    response = await client.patch(USER.format(counselor.id), json={"telecaller_profile": {"employee_id": emp()}})
    assert response.status_code == 422 and response.json()["detail"] == "Only a telecaller has a telecaller profile"


@pytest.mark.asyncio
async def test_division_admin_cannot_edit_the_other_team(client, db_session):
    _, _, body = await _created(client, db_session, team="overseas")
    await login(client, await make_user(db_session, "it_admin", "it"))
    assert (await client.patch(USER.format(body["id"]), json={"full_name": "X"})).status_code == 403
    await login(client, await make_user(db_session, "overseas_admin", "overseas"))
    assert (await client.patch(USER.format(body["id"]), json={"telecaller_profile": {"employee_id": emp()}})).status_code == 200
