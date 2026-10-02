"""AGN-008 AC17 -- the spec §7 abuse cases. Each asserts the stated code AND that nothing was written.

Abuse 5 (stale), 6 (throttle) and 7 (archived) are pinned in the feature files, not repeated here:
- test_agn_008_status.py: the stale-status tests
- test_agn_008_create.py: the throttle tests
- test_agn_008_edit.py: the archived-student tests
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models import AgentCommission, AgentOrgMember, ApplicationStatusHistory, AuditLog, OverseasApplication, User
from tests.agn001_helpers import client_for, mk_user
from tests.agn008_helpers import APPS, agency_world, mk_application


@pytest_asyncio.fixture
async def world(db_session):
    w = await agency_world(db_session)
    w["app"] = await mk_application(db_session, agent=w["master"], university=w["university"], record=w["record"])
    return w


async def _nothing_written(db, app_id):
    for model, column in ((ApplicationStatusHistory, ApplicationStatusHistory.application_id), (AgentCommission, AgentCommission.application_id)):
        assert await db.scalar(select(func.count()).select_from(model).where(column == app_id)) == 0
    assert await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == str(app_id))) == 0


@pytest.mark.asyncio
async def test_staff_cannot_reach_another_staff_members_application(db_session, world):  # abuse 1
    async with client_for(world["other_staff"]["user"].email) as c:
        for call in (c.get(f"{APPS}/{world['app'].id}"), c.patch(f"{APPS}/{world['app'].id}", json={"intake": "X"}), c.post(f"{APPS}/{world['app'].id}/status", json={"to_status": "offer"})):
            assert (await call).status_code == 404
    await _nothing_written(db_session, world["app"].id)


@pytest.mark.asyncio
async def test_other_org_cannot_post_this_orgs_student(db_session, world):  # abuse 2
    async with client_for(world["other"]["master"].email) as c:
        r = await c.post(APPS, json={"agent_student_id": str(world["record"].id), "university_id": str(world["university"].id), "intake": "Fall"})
    assert r.status_code == 404
    assert await db_session.scalar(select(func.count()).select_from(OverseasApplication).where(OverseasApplication.agent_id == world["other"]["master"].id)) == 0


@pytest.mark.asyncio
async def test_agent_cannot_set_enrolled(db_session, world):  # abuse 3
    async with client_for(world["master"].email) as c:
        assert (await c.post(f"{APPS}/{world['app'].id}/status", json={"to_status": "enrolled"})).status_code == 403
    await _nothing_written(db_session, world["app"].id)


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{"agent_id": str(uuid.uuid4())}, {"status": "enrolled"}, {"university_id": str(uuid.uuid4())}, {"student_id": str(uuid.uuid4())}, {"school_student_id": str(uuid.uuid4())}])
async def test_mass_assignment_is_422(db_session, world, body):  # abuse 4
    async with client_for(world["master"].email) as c:
        assert (await c.patch(f"{APPS}/{world['app'].id}", json=body)).status_code == 422
    await _nothing_written(db_session, world["app"].id)


@pytest.mark.asyncio
async def test_deactivated_staff_is_refused(db_session, world):  # abuse 8
    member = await db_session.get(AgentOrgMember, world["staff"]["member"].id, populate_existing=True)
    async with client_for(world["staff"]["user"].email) as c:
        member.status = "deactivated"
        user = await db_session.get(User, world["staff"]["user"].id, populate_existing=True)
        user.active = False
        await db_session.commit()
        r = await c.get(APPS)
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["counselor", "university_rep", "overseas_admin"])
async def test_other_roles_are_refused(db_session, world, role):  # abuse 9
    user = await mk_user(db_session, role=role)
    async with client_for(user.email) as c:
        assert (await c.post(f"{APPS}/{world['app'].id}/status", json={"to_status": "offer"})).status_code == 403
    await _nothing_written(db_session, world["app"].id)


@pytest.mark.asyncio
async def test_responses_never_carry_internal_ids_or_contact_details(world):
    async with client_for(world["master"].email) as c:
        listing = (await c.get(APPS)).json()["items"]
        one = (await c.get(f"{APPS}/{world['app'].id}")).json()["application"]
    for body in (*listing, one):
        assert not {"agent_id", "student_id", "counselor_id", "school_student_id", "email", "phone"} & set(body)
