"""AGN-002 -- staff members of an agent organisation, and a per-user session version.

Revision ID: 0047_agent_org_staff
Revises: 0046_agent_orgs

docs/superpowers/specs/2026-09-30-agn-002-staff-logins-design.md §4 (DEC-SCOPE-040). Additive: `agent_orgs.staff_seq` and
`users.session_version` (server default 0, so no backfill), the member role check widened to master|staff, and member numbers
made unique per role (M001 and S001 coexist). No existing row changes. Every step checks the live schema first (columns and
constraints are only added or dropped when that is still needed), so a database whose tables were created from the current models
-- `auto_create_schema`, or an earlier migration's `create_all` -- still upgrades. `downgrade()` refuses while a staff member
exists: it never silently deletes logins.
"""

import sqlalchemy as sa

from alembic import op

revision = "0047_agent_org_staff"
down_revision = "0046_agent_orgs"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    if op.get_context().as_sql:
        return set()
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _constraints(table: str) -> set[str]:
    """Names of the table's unique + check constraints (offline SQL generation assumes the 0046 schema)."""
    if op.get_context().as_sql:
        return {"uq_agent_org_members_org_seq", "ck_agent_org_members_role"} if table == "agent_org_members" else set()
    inspector = sa.inspect(op.get_bind())
    return {c["name"] for c in inspector.get_unique_constraints(table)} | {c["name"] for c in inspector.get_check_constraints(table)}


def assert_no_staff(bind) -> None:
    if bind.execute(sa.text("SELECT 1 FROM agent_org_members WHERE role = 'staff' LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0047_agent_org_staff: staff members exist. Remove them deliberately first.")


def upgrade() -> None:
    if "staff_seq" not in _columns("agent_orgs"):
        op.add_column("agent_orgs", sa.Column("staff_seq", sa.Integer(), nullable=False, server_default="0"))
    if "ck_agent_orgs_staff_seq" not in _constraints("agent_orgs"):
        op.create_check_constraint("ck_agent_orgs_staff_seq", "agent_orgs", "staff_seq >= 0")
    members = _constraints("agent_org_members")
    # The role check keeps its name; recreate it so it always allows staff, whichever form it has now.
    if "ck_agent_org_members_role" in members:
        op.drop_constraint("ck_agent_org_members_role", "agent_org_members", type_="check")
    op.create_check_constraint("ck_agent_org_members_role", "agent_org_members", "role IN ('master', 'staff')")
    if "uq_agent_org_members_org_seq" in members:
        op.drop_constraint("uq_agent_org_members_org_seq", "agent_org_members", type_="unique")
    if "uq_agent_org_members_org_role_seq" not in members:
        op.create_unique_constraint("uq_agent_org_members_org_role_seq", "agent_org_members", ["org_id", "role", "seq"])
    if "session_version" not in _columns("users"):
        op.add_column("users", sa.Column("session_version", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    assert_no_staff(op.get_bind())
    op.drop_column("users", "session_version")
    op.drop_constraint("uq_agent_org_members_org_role_seq", "agent_org_members", type_="unique")
    op.create_unique_constraint("uq_agent_org_members_org_seq", "agent_org_members", ["org_id", "seq"])
    op.drop_constraint("ck_agent_org_members_role", "agent_org_members", type_="check")
    op.create_check_constraint("ck_agent_org_members_role", "agent_org_members", "role = 'master'")
    op.drop_constraint("ck_agent_orgs_staff_seq", "agent_orgs", type_="check")
    op.drop_column("agent_orgs", "staff_seq")
