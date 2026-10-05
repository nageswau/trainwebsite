"""AGN-012 AC8 -- Master: the organisation; Staff: assigned students only (V1); everyone else refused; refusals write nothing."""

import pytest
import pytest_asyncio

from tests.agn001_helpers import client_for, mk_user
from tests.agn012_helpers import VISA, count_cases, mk_case, visa_audits, visa_world

START = {"expected_status": "offer", "checklist": ["Passport"]}


@pytest_asyncio.fixture
async def world(db_session):
    return await visa_world(db_session)


@pytest.mark.asyncio
@pytest.mark.parametrize("who", ["master", "staff", "plain"])
async def test_master_and_staff_in_scope_start_and_update(db_session, who):
    w = await visa_world(db_session)
    if who == "plain":  # a staff member without Verify, assigned this student
        w["record"].assigned_member_id = w["plain"]["member"].id
        db_session.add(w["record"])
        await db_session.commit()
    email = w["master"].email if who == "master" else w[who]["user"].email
    async with client_for(email) as c:
        assert (await c.post(VISA.format(w["app"].id), json=START)).status_code == 201
        assert (await c.patch(VISA.format(w["app"].id), json={"expected_stage": "checklist", "appointment_date": "2027-05-01"})).status_code == 200


@pytest.mark.asyncio
async def test_staff_out_of_scope_is_404_and_writes_nothing(db_session, world):
    await mk_case(db_session, world["app"])
    world["record"].assigned_member_id = None  # reassigned away after the screen loaded
    db_session.add(world["record"])
    await db_session.commit()
    async with client_for(world["staff"]["user"].email) as c:
        assert (await c.patch(VISA.format(world["app"].id), json={"expected_stage": "checklist", "appointment_date": "2027-05-01"})).status_code == 404
    assert await visa_audits(db_session, world["app"]) == []


@pytest.mark.asyncio
async def test_other_agency_is_404_for_both_routes(db_session, world):
    async with client_for(world["other"]["master"].email) as c:
        assert (await c.post(VISA.format(world["app"].id), json=START)).status_code == 404
        await mk_case(db_session, world["app"])
        assert (await c.patch(VISA.format(world["app"].id), json={"expected_stage": "checklist", "to_stage": "documentation"})).status_code == 404
    assert await count_cases(db_session, world["app"]) == 1 and await visa_audits(db_session, world["app"]) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["counselor", "overseas_admin", "overseas_student", "super_admin"])
async def test_non_agents_are_403(db_session, world, role):
    user = await mk_user(db_session, role=role)
    async with client_for(user.email) as c:
        assert (await c.post(VISA.format(world["app"].id), json=START)).status_code == 403
    assert await count_cases(db_session, world["app"]) == 0


@pytest.mark.asyncio
async def test_the_linked_student_cannot_use_the_agency_route(world):
    # A student with a login linked to the agency is an overseas_student: refused by the agency gate.
    async with client_for(world["linked_user"].email) as c:
        assert (await c.post(VISA.format(world["app"].id), json=START)).status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_is_401(client, db_session, world):
    assert (await client.post(VISA.format(world["app"].id), json=START)).status_code == 401
    assert (await client.patch(VISA.format(world["app"].id), json={"expected_stage": "checklist"})).status_code == 401
    assert await count_cases(db_session, world["app"]) == 0


@pytest.mark.asyncio
async def test_unknown_application_is_404(world):
    async with client_for(world["master"].email) as c:
        assert (await c.post(VISA.format("00000000-0000-0000-0000-000000000000"), json=START)).status_code == 404
