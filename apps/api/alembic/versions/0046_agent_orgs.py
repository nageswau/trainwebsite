"""AGN-001 -- agent organisations (tenants) and their Master members.

Revision ID: 0046_agent_orgs
Revises: 0045_psychometric_result_fields

docs/superpowers/specs/2026-09-28-agn-001-multi-tenant-agent-crm-design.md §4 (DEC-SCOPE-038 D10; cut as 0045_agent_orgs,
re-chained on ENH-027's 0045 when main was merged). Creates two tables and
backfills one organisation + Master M001 per existing agent. No existing table or row is altered. The backfill only touches
agents that have no membership yet, so it is safe if the tables were already created by `auto_create_schema` and safe to
re-run. `downgrade()` drops only the two new tables.
"""

import re
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0046_agent_orgs"
down_revision = "0045_psychometric_result_fields"
branch_labels = None
depends_on = None

_LATIN = re.compile(r"[A-Za-z]")


# Verbatim copies of app.services.agent_orgs (a migration never imports live app code).
def _prefix_base(name):
    letters = _LATIN.findall(name or "")
    return "AGT" if not letters else "".join(letters[:3]).upper().ljust(3, "X")


def _pick(base, taken):
    if base not in taken:
        return base
    n = 2
    while f"{base}{n}" in taken:
        n += 1
    return f"{base}{n}"


def upgrade() -> None:
    bind = op.get_bind()
    existing = set() if op.get_context().as_sql else set(sa.inspect(bind).get_table_names())
    if "agent_orgs" not in existing:
        op.create_table(
            "agent_orgs",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("name", sa.String(160), nullable=False),
            sa.Column("prefix", sa.String(8), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("master_seq", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status_changed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("prefix", name="uq_agent_orgs_prefix"),
            sa.CheckConstraint("status IN ('pending', 'active', 'rejected', 'suspended')", name="ck_agent_orgs_status"),
            sa.CheckConstraint("master_seq >= 0", name="ck_agent_orgs_master_seq"),
        )
        op.create_index("ix_agent_orgs_status", "agent_orgs", ["status"])
    if "agent_org_members" not in existing:
        op.create_table(
            "agent_org_members",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_orgs.id"), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("role", sa.String(20), nullable=False, server_default="master"),
            sa.Column("seq", sa.Integer(), nullable=False),
            sa.Column("code", sa.String(16), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("invited_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("deactivated_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("user_id", name="uq_agent_org_members_user"),
            sa.UniqueConstraint("code", name="uq_agent_org_members_code"),
            sa.UniqueConstraint("org_id", "seq", name="uq_agent_org_members_org_seq"),
            sa.CheckConstraint("role = 'master'", name="ck_agent_org_members_role"),
            sa.CheckConstraint("status IN ('active', 'deactivated')", name="ck_agent_org_members_status"),
        )
        op.create_index("ix_agent_org_members_org_id", "agent_org_members", ["org_id"])
    if op.get_context().as_sql:
        return  # offline SQL generation: no data to backfill
    _backfill(bind)


def _backfill(bind) -> None:
    """D10: each agent without a membership becomes M001 of its own organisation; approved -> active, anything else -> pending."""
    taken = {row[0] for row in bind.execute(sa.text("SELECT prefix FROM agent_orgs"))}
    agents = bind.execute(sa.text(
        "SELECT u.id, u.full_name, u.profile->>'agency_name' AS agency_name, "
        "(SELECT a.approval_status FROM user_role_assignments a WHERE a.user_id = u.id AND a.division = 'overseas' AND a.role = 'agent') AS approval "
        "FROM users u WHERE u.role = 'agent' AND NOT EXISTS (SELECT 1 FROM agent_org_members m WHERE m.user_id = u.id) "
        "ORDER BY u.created_at, u.id"
    )).all()
    for user_id, full_name, agency_name, approval in agents:
        name = (agency_name or "").strip() or full_name
        prefix = _pick(_prefix_base(name), taken)
        taken.add(prefix)
        org_id = uuid.uuid4()
        bind.execute(
            sa.text("INSERT INTO agent_orgs (id, name, prefix, status, master_seq) VALUES (:id, :name, :prefix, :status, 1)"),
            {"id": org_id, "name": name[:160], "prefix": prefix, "status": "active" if approval == "approved" else "pending"},
        )
        bind.execute(
            sa.text("INSERT INTO agent_org_members (id, org_id, user_id, role, seq, code, status) VALUES (:id, :org, :user, 'master', 1, :code, 'active')"),
            {"id": uuid.uuid4(), "org": org_id, "user": user_id, "code": f"{prefix}-M001"},
        )


def downgrade() -> None:
    op.drop_index("ix_agent_org_members_org_id", table_name="agent_org_members")
    op.drop_table("agent_org_members")
    op.drop_index("ix_agent_orgs_status", table_name="agent_orgs")
    op.drop_table("agent_orgs")
