"""AGN-003 -- migration 0048: per-staff permission flags (spec §5, AGN-003-AC09)."""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import inspect

from app.models import AgentOrgMember
from tests.agn001_helpers import mk_active_org
from tests.agn002_helpers import mk_staff

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_agn_003_migration_0048", VERSIONS / "0048_agent_staff_permissions.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

FLAGS = ("can_verify_documents", "can_view_reports")


def test_migration_follows_0047():
    assert _migration.revision == "0048_agent_staff_permissions"
    assert _migration.down_revision == "0047_agent_org_staff"


@pytest.mark.asyncio
async def test_flags_are_not_null_with_a_false_server_default(db_session):
    def _cols(sync_conn):
        return {c["name"]: c for c in inspect(sync_conn).get_columns("agent_org_members")}

    cols = await (await db_session.connection()).run_sync(_cols)
    for name in FLAGS:
        assert cols[name]["nullable"] is False
        assert "false" in str(cols[name]["default"]).lower()


@pytest.mark.asyncio
async def test_new_members_start_with_both_flags_off(db_session):
    ctx = await mk_active_org(db_session, name="Flags Default")
    staff = await mk_staff(db_session, ctx["org"])
    for member_id in (staff["member"].id, ctx["member"].id):
        member = await db_session.get(AgentOrgMember, member_id, populate_existing=True)
        assert (member.can_verify_documents, member.can_view_reports) == (False, False)


@pytest.mark.asyncio
async def test_mk_staff_can_switch_flags_on(db_session):
    ctx = await mk_active_org(db_session, name="Flags On")
    staff = await mk_staff(db_session, ctx["org"], can_verify_documents=True, can_view_reports=True)
    member = await db_session.get(AgentOrgMember, staff["member"].id, populate_existing=True)
    assert (member.can_verify_documents, member.can_view_reports) == (True, True)
