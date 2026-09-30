"""AGN-004 -- students with no login on agent_students, plus AGN-002's staff member pieces.

Revision ID: 0047_agent_students_crm
Revises: 0046_agent_orgs

docs/superpowers/specs/2026-09-30-agn-004-agent-students-design.md §4 (DEC-SCOPE-041). The staff pieces (agent_orgs.staff_seq,
member role master|staff, member numbers unique per role) are identical to AGN-002's 0047_agent_org_staff and guarded, so whichever
of the two runs second skips them. agent_students gains nullable identity, assignment and archive columns; student_id becomes
nullable. No existing row changes. downgrade() refuses while a student with no login, an assignment or a staff member exists: it never
silently deletes students or logins.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0047_agent_students_crm"
down_revision = "0046_agent_orgs"
branch_labels = None
depends_on = None

STUDENT_COLUMNS = (
    ("full_name", sa.String(160)),
    ("email", sa.String(320)),
    ("phone", sa.String(40)),
    ("phone_digits", sa.String(20)),
    ("date_of_birth", sa.Date()),
    ("highest_qualification", sa.String(200)),
    ("institution", sa.String(200)),
    ("graduation_year", sa.SmallInteger()),
    ("preferred_country", sa.String(120)),
    ("preferred_course", sa.String(200)),
    ("preferred_intake", sa.String(40)),
    ("notes", sa.Text()),
    ("archived_at", sa.DateTime(timezone=True)),
)
FK_COLUMNS = (
    ("assigned_member_id", "agent_org_members.id"),
    ("archived_by_user_id", "users.id"),
    ("updated_by_user_id", "users.id"),
)
INDEXES = (
    ("ix_agent_students_agent_status", ["agent_id", "status"]),
    ("ix_agent_students_agent_phone_digits", ["agent_id", "phone_digits"]),
    ("ix_agent_students_assigned_member", ["assigned_member_id"]),
)


def _columns(table: str) -> set[str]:
    if op.get_context().as_sql:
        return set()
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _unique_constraints(table: str) -> set[str]:
    if op.get_context().as_sql:
        return {"uq_agent_org_members_org_seq"}
    return {c["name"] for c in sa.inspect(op.get_bind()).get_unique_constraints(table)}


def _check_constraints(table: str) -> set[str]:
    if op.get_context().as_sql:
        return set()
    return {c["name"] for c in sa.inspect(op.get_bind()).get_check_constraints(table)}


def _indexes(table: str) -> set[str]:
    if op.get_context().as_sql:
        return set()
    return {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(table)}


def _refuse_if(bind, sql: str, message: str) -> None:
    if bind.execute(sa.text(sql)).first():
        raise RuntimeError(message)


def upgrade() -> None:
    # --- AGN-002 staff pieces (identical names; guarded) ---
    # 0001/0003 run Base.metadata.create_all from the CURRENT models, so a database built from scratch already has every
    # column, CHECK and index below by the time this runs: each one is created only when missing.
    if "staff_seq" not in _columns("agent_orgs"):
        op.add_column("agent_orgs", sa.Column("staff_seq", sa.Integer(), nullable=False, server_default="0"))
    if "ck_agent_orgs_staff_seq" not in _check_constraints("agent_orgs"):
        op.create_check_constraint("ck_agent_orgs_staff_seq", "agent_orgs", "staff_seq >= 0")
    op.drop_constraint("ck_agent_org_members_role", "agent_org_members", type_="check")
    op.create_check_constraint("ck_agent_org_members_role", "agent_org_members", "role IN ('master', 'staff')")
    if "uq_agent_org_members_org_seq" in _unique_constraints("agent_org_members"):
        op.drop_constraint("uq_agent_org_members_org_seq", "agent_org_members", type_="unique")
        op.create_unique_constraint("uq_agent_org_members_org_role_seq", "agent_org_members", ["org_id", "role", "seq"])

    # --- AGN-004 agent_students ---
    if not op.get_context().as_sql:
        _refuse_if(op.get_bind(), "SELECT 1 FROM agent_students WHERE status NOT IN ('active', 'archived') LIMIT 1", "agent_students has a status other than active/archived; fix it before 0047")
    existing = _columns("agent_students")
    for name, type_ in STUDENT_COLUMNS:
        if name not in existing:
            op.add_column("agent_students", sa.Column(name, type_, nullable=True))
    for name, target in FK_COLUMNS:
        if name not in existing:
            op.add_column("agent_students", sa.Column(name, postgresql.UUID(as_uuid=True), sa.ForeignKey(target), nullable=True))
    op.alter_column("agent_students", "student_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)
    checks = _check_constraints("agent_students")
    if "ck_agent_students_identity" not in checks:
        op.create_check_constraint("ck_agent_students_identity", "agent_students", "student_id IS NOT NULL OR full_name IS NOT NULL")
    if "ck_agent_students_status" not in checks:
        op.create_check_constraint("ck_agent_students_status", "agent_students", "status IN ('active', 'archived')")
    indexes = _indexes("agent_students")
    for name, cols in INDEXES:
        if name not in indexes:
            op.create_index(name, "agent_students", cols)
    if "ix_agent_students_agent_email_lower" not in indexes:
        op.create_index("ix_agent_students_agent_email_lower", "agent_students", ["agent_id", sa.text("lower(email)")])


def downgrade() -> None:
    bind = op.get_bind()
    _refuse_if(bind, "SELECT 1 FROM agent_students WHERE student_id IS NULL LIMIT 1", "Cannot downgrade 0047_agent_students_crm: students with no login exist. Remove them deliberately first.")
    _refuse_if(bind, "SELECT 1 FROM agent_students WHERE assigned_member_id IS NOT NULL LIMIT 1", "Cannot downgrade 0047_agent_students_crm: assigned students exist. Unassign them deliberately first.")
    # AGN-002's rule, checked before anything is dropped: never turn staff into Masters by a rollback.
    _refuse_if(bind, "SELECT 1 FROM agent_org_members WHERE role = 'staff' LIMIT 1", "Cannot downgrade 0047_agent_students_crm: staff members exist. Remove them deliberately first.")
    op.drop_index("ix_agent_students_agent_email_lower", table_name="agent_students")
    for name, _ in INDEXES:
        op.drop_index(name, table_name="agent_students")
    op.drop_constraint("ck_agent_students_status", "agent_students", type_="check")
    op.drop_constraint("ck_agent_students_identity", "agent_students", type_="check")
    op.alter_column("agent_students", "student_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)
    for name, _ in reversed(FK_COLUMNS):
        op.drop_column("agent_students", name)
    for name, _ in reversed(STUDENT_COLUMNS):
        op.drop_column("agent_students", name)
    op.drop_constraint("uq_agent_org_members_org_role_seq", "agent_org_members", type_="unique")
    op.create_unique_constraint("uq_agent_org_members_org_seq", "agent_org_members", ["org_id", "seq"])
    op.drop_constraint("ck_agent_org_members_role", "agent_org_members", type_="check")
    op.create_check_constraint("ck_agent_org_members_role", "agent_org_members", "role = 'master'")
    op.drop_constraint("ck_agent_orgs_staff_seq", "agent_orgs", type_="check")
    op.drop_column("agent_orgs", "staff_seq")
