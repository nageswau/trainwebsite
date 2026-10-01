"""AGN-002 -- migration 0047: staff members, per-role numbering, staff counter, session version (spec §4)."""

import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.models import AgentOrg, AgentOrgMember, User
from tests.agn001_helpers import mk_user

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_agn_002_migration_0047", VERSIONS / "0047_agent_org_staff.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)


def _org(**overrides) -> AgentOrg:
    return AgentOrg(**{"name": "Staff Chk", "prefix": f"Q{uuid.uuid4().hex[:6].upper()}", "status": "active", "master_seq": 1, **overrides})


def test_migration_follows_0046_and_is_the_single_head():
    assert _migration.revision == "0047_agent_org_staff"
    assert _migration.down_revision == "0046_agent_orgs"
    parents = {}
    for file in VERSIONS.glob("*.py"):
        lines = file.read_text(encoding="utf-8").splitlines()
        rev = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("revision =")), None)
        parent = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("down_revision =")), None)
        if rev:
            parents[rev] = parent
    assert len(set(parents) - set(parents.values())) == 1


@pytest.mark.asyncio
async def test_new_columns_default_to_zero(db_session):
    user = await mk_user(db_session, role="agent")
    org = _org()
    db_session.add(org)
    await db_session.commit()
    assert (await db_session.get(User, user.id, populate_existing=True)).session_version == 0
    assert (await db_session.get(AgentOrg, org.id, populate_existing=True)).staff_seq == 0

    def _cols(sync_conn):
        return {t: {c["name"]: c for c in inspect(sync_conn).get_columns(t)} for t in ("users", "agent_orgs")}

    cols = await (await db_session.connection()).run_sync(_cols)
    assert cols["users"]["session_version"]["nullable"] is False
    assert cols["agent_orgs"]["staff_seq"]["nullable"] is False


@pytest.mark.asyncio
async def test_a_staff_member_and_a_master_may_share_a_number(db_session):
    master, staff = await mk_user(db_session, role="agent"), await mk_user(db_session, role="agent")
    org = _org(staff_seq=1)
    db_session.add(org)
    await db_session.flush()
    db_session.add_all([
        AgentOrgMember(org_id=org.id, user_id=master.id, role="master", seq=1, code=f"{org.prefix}-M001", status="active"),
        AgentOrgMember(org_id=org.id, user_id=staff.id, role="staff", seq=1, code=f"{org.prefix}-S001", status="active"),
    ])
    await db_session.commit()


@pytest.mark.asyncio
async def test_two_staff_members_may_not_share_a_number(db_session):
    a, b = await mk_user(db_session, role="agent"), await mk_user(db_session, role="agent")
    org = _org(staff_seq=1)
    db_session.add(org)
    await db_session.flush()
    db_session.add(AgentOrgMember(org_id=org.id, user_id=a.id, role="staff", seq=1, code=f"{org.prefix}-S001", status="active"))
    await db_session.flush()
    db_session.add(AgentOrgMember(org_id=org.id, user_id=b.id, role="staff", seq=1, code=f"{org.prefix}-S001X", status="active"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_staff_seq_cannot_be_negative(db_session):
    db_session.add(_org(staff_seq=-1))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_downgrade_guard_refuses_while_staff_exist(db_session):
    staff = await mk_user(db_session, role="agent")
    org = _org(staff_seq=1)
    db_session.add(org)
    await db_session.flush()
    db_session.add(AgentOrgMember(org_id=org.id, user_id=staff.id, role="staff", seq=1, code=f"{org.prefix}-S001", status="active"))
    await db_session.commit()
    conn = await db_session.connection()
    with pytest.raises(RuntimeError, match="staff members exist"):
        await conn.run_sync(_migration.assert_no_staff)
    assert await db_session.scalar(text("SELECT count(*) FROM agent_org_members WHERE role = 'staff'")) >= 1
