"""AGN-004 -- model constraints added by migration 0047_agent_students_crm (spec §4)."""

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import AgentOrg, AgentOrgMember, AgentStudent
from tests.agn001_helpers import mk_active_org, mk_user
from tests.agn004_helpers import mk_staff


@pytest.mark.asyncio
async def test_staff_member_role_is_allowed_and_numbered_apart_from_masters(db_session):
    ctx = await mk_active_org(db_session, name="Schema Staff")
    staff = await mk_staff(db_session, ctx["org"])
    assert staff["member"].code.endswith("-S001") and ctx["member"].code.endswith("-M001")
    assert staff["member"].seq == ctx["member"].seq == 1  # uq_agent_org_members_org_role_seq lets M001 and S001 coexist


@pytest.mark.asyncio
async def test_member_role_check_rejects_unknown_roles(db_session):
    user = await mk_user(db_session, role="agent")
    org = AgentOrg(name="Chk", prefix=f"Q{uuid.uuid4().hex[:6].upper()}", status="pending", master_seq=1)
    db_session.add(org)
    await db_session.flush()
    db_session.add(AgentOrgMember(org_id=org.id, user_id=user.id, role="owner", seq=1, code=f"{org.prefix}-M001", status="active"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_student_without_login_needs_a_name(db_session):
    ctx = await mk_active_org(db_session, name="Schema Identity")
    db_session.add(AgentStudent(agent_id=ctx["master"].id, student_id=None, status="active"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_student_status_is_active_or_archived(db_session):
    ctx = await mk_active_org(db_session, name="Schema Status")
    db_session.add(AgentStudent(agent_id=ctx["master"].id, student_id=None, full_name="Asha", status="deleted"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_student_without_login_is_stored_with_no_user(db_session):
    ctx = await mk_active_org(db_session, name="Schema Store")
    row = AgentStudent(agent_id=ctx["master"].id, student_id=None, full_name="Asha Rao", status="active", preferred_country="Canada")
    db_session.add(row)
    await db_session.commit()
    assert row.student_id is None and row.full_name == "Asha Rao"
