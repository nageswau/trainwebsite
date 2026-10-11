"""rec-029 -- campus recruitment drives: recruitment_drives, drive_requirements, recruitment_drive_code_seq and job_applications.drive_id.

Revision ID: 0148_recruitment_drives
Revises: 0147_recruiter_revenue

docs/superpowers/specs/2026-10-11-rec-029-campus-drives-design.md §2 (DEC-SCOPE-177). Additive: two new tables and one nullable column; no
existing row read or written (no backfill). 0001 builds a fresh database from the current models, which already carry all of it, so
each piece is created only when missing. STATUSES / CHECKS are frozen copies of app.models.RECRUITMENT_DRIVE_* (test_rec_029_migration).
downgrade() refuses while any drive exists: recorded drives and their tags are never dropped silently.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0148_recruitment_drives"
down_revision = "0147_recruiter_revenue"
branch_labels = None
depends_on = None

DRIVES, LINKS, APPLICATIONS = "recruitment_drives", "drive_requirements", "job_applications"
SEQ = "recruitment_drive_code_seq"
STATUSES = ("planned", "completed", "cancelled")
CHECKS = {
    "ck_recruitment_drives_status": f"status IN ({', '.join(repr(s) for s in STATUSES)})",
    "ck_recruitment_drives_college": "(college_org_id IS NULL) <> (college_name IS NULL)",
    "ck_recruitment_drives_counts": "students_registered >= 0 AND students_attended >= 0",
    "ck_recruitment_drives_attended": "students_attended <= students_registered",
    "ck_recruitment_drives_vacancies": "vacancies >= 1",
}


def _fk(target: str) -> sa.ForeignKey:
    return sa.ForeignKey(target, ondelete="RESTRICT")


def upgrade() -> None:
    op.execute(f"CREATE SEQUENCE IF NOT EXISTS {SEQ}")
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(op.get_bind())
    tables = set() if offline else set(inspector.get_table_names())
    uuid = postgresql.UUID(as_uuid=True)
    if DRIVES not in tables:
        op.create_table(
            DRIVES,
            sa.Column("id", uuid, primary_key=True),
            sa.Column("drive_code", sa.String(20), nullable=False),
            sa.Column("company_id", uuid, _fk("companies.id"), nullable=False),
            sa.Column("college_org_id", uuid, _fk("bdm_organizations.id"), nullable=True),
            sa.Column("college_name", sa.String(200), nullable=True),
            sa.Column("drive_date", sa.Date(), nullable=False),
            sa.Column("job_role", sa.String(150), nullable=False),
            sa.Column("vacancies", sa.Integer(), nullable=False),
            sa.Column("eligibility", sa.String(1000), nullable=True),
            sa.Column("students_registered", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("students_attended", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'planned'")),
            sa.Column("created_by_user_id", uuid, _fk("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("drive_code", name="uq_recruitment_drives_code"),
            *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
        )
        op.create_index("ix_recruitment_drives_company_date", DRIVES, ["company_id", "drive_date"])
        op.create_index("ix_recruitment_drives_date", DRIVES, ["drive_date"])
    if LINKS not in tables:
        op.create_table(
            LINKS,
            sa.Column("drive_id", uuid, _fk("recruitment_drives.id"), primary_key=True),
            sa.Column("job_id", uuid, _fk("jobs.id"), primary_key=True),
        )
        op.create_index("ix_drive_requirements_job", LINKS, ["job_id"])
    if offline or "drive_id" not in {c["name"] for c in inspector.get_columns(APPLICATIONS)}:
        op.add_column(APPLICATIONS, sa.Column("drive_id", uuid, _fk("recruitment_drives.id"), nullable=True))
        op.create_index("ix_job_applications_drive", APPLICATIONS, ["drive_id"])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {DRIVES} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0148_recruitment_drives: recruitment drives exist. Clear them deliberately first.")
    op.drop_index("ix_job_applications_drive", table_name=APPLICATIONS)
    op.drop_column(APPLICATIONS, "drive_id")
    op.drop_table(LINKS)
    op.drop_table(DRIVES)
    op.execute(f"DROP SEQUENCE IF EXISTS {SEQ}")
