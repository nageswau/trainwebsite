"""bdm-002 -- bdm_organizations + bdm_organization_contacts + bdm_organization_code_seq.

Revision ID: 0066_bdm_organizations
Revises: 0065_agent_notifications

docs/superpowers/specs/2026-10-03-bdm-002-organization-crm-design.md §4 (DEC-SCOPE-060). Adds two tables and one sequence; no existing
row is read or written. 0001 builds a fresh database from the current models (which carry both tables and the sequence), so creation
is guarded (0061's idiom) and the sequence is created IF NOT EXISTS. downgrade() refuses while organizations exist: they are the only
record of each institution, its contacts and its assignment.

Re-chained 2026-10-03 on merging `main`: cut as `0064_bdm_organizations` after `0063_agent_visa_details`, but AGN-011's
`0064_application_deposits` and AGN-017's `0065_agent_notifications` reached `main` first, so this revision is now
`0066_bdm_organizations` after 0065 (one head). A database stamped at `0064_bdm_organizations` is re-stamped with
`alembic stamp --purge 0063_agent_visa_details` then `upgrade head` (the guarded create makes the re-run harmless).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0066_bdm_organizations"
down_revision = "0065_agent_notifications"
branch_labels = None
depends_on = None

ORGS = "bdm_organizations"
CONTACTS = "bdm_organization_contacts"
SEQ = "bdm_organization_code_seq"
ORG_TYPES = "'college', 'university', 'agent', 'school', 'corporate', 'training_institute', 'other'"
ROLES = "'principal', 'dean', 'hod', 'placement_officer', 'counselor', 'management', 'owner', 'other'"


def _uuid(name: str, *args, **kwargs) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), *args, nullable=False, **kwargs)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.execute(f"CREATE SEQUENCE IF NOT EXISTS {SEQ}")
    if not op.get_context().as_sql and ORGS in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        ORGS,
        _uuid("id", primary_key=True),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("org_type", sa.String(30), nullable=False),
        sa.Column("bdm_type", sa.String(20), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("name_key", sa.String(200), nullable=False),
        sa.Column("city", sa.String(120), nullable=False),
        sa.Column("city_key", sa.String(120), nullable=False),
        sa.Column("state", sa.String(120), nullable=True),
        sa.Column("phone", sa.String(30), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("website", sa.String(255), nullable=True),
        sa.Column("existing_partner", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("courses_interested", sa.String(1000), nullable=True),
        sa.Column("student_count", sa.Integer(), nullable=True),
        _uuid("assigned_bdm_user_id", sa.ForeignKey("users.id", ondelete="RESTRICT")),
        _uuid("created_by_user_id", sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("code", name="uq_bdm_organizations_code"),
        sa.CheckConstraint(f"org_type IN ({ORG_TYPES})", name="ck_bdm_organizations_org_type"),
        sa.CheckConstraint("bdm_type IN ('agent', 'school', 'college')", name="ck_bdm_organizations_bdm_type"),
        sa.CheckConstraint("student_count IS NULL OR student_count >= 0", name="ck_bdm_organizations_student_count"),
    )
    op.create_index("ix_bdm_organizations_type_assignee", ORGS, ["bdm_type", "assigned_bdm_user_id"])
    op.create_index("ix_bdm_organizations_duplicate_key", ORGS, ["bdm_type", "name_key", "city_key"])
    op.create_table(
        CONTACTS,
        _uuid("id", primary_key=True),
        _uuid("organization_id", sa.ForeignKey(f"{ORGS}.id", ondelete="RESTRICT")),
        sa.Column("position", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("designation", sa.String(120), nullable=True),
        sa.Column("role", sa.String(30), nullable=True),
        sa.Column("phone", sa.String(30), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.false(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(f"role IS NULL OR role IN ({ROLES})", name="ck_bdm_organization_contacts_role"),
    )
    op.create_index("ix_bdm_organization_contacts_org", CONTACTS, ["organization_id"])
    op.create_index("uq_bdm_organization_contacts_primary", CONTACTS, ["organization_id"], unique=True, postgresql_where=sa.text("is_primary"))


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {ORGS} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0066_bdm_organizations: BDM organizations exist. Remove them deliberately first.")
    op.drop_table(CONTACTS)
    op.drop_table(ORGS)
    op.execute(f"DROP SEQUENCE IF EXISTS {SEQ}")
