"""hrc-005 -- vacancy fields completion: requisition reference, source, certifications, country/state/city, relocation/travel, pay
currency/period, benefits, hiring manager, expected joining date, last updated by; and the duplicate check's index.

Revision ID: 0258_vacancy_fields
Revises: 0257_job_approval

docs/superpowers/specs/2026-11-04-hrc-005-vacancy-fields-duplicates-design.md (DEC-SCOPE-381). Nullable columns only, no backfill (V3:
legacy free-text locations stay as they are). 0001 builds a fresh database from the current models, which already carry them, so each
step runs only when missing (0222's idiom). CHECKS and TITLE_KEY are frozen copies of the model's strings at this revision.
"""

import sqlalchemy as sa

from alembic import op

revision = "0258_vacancy_fields"
down_revision = "0257_job_approval"
branch_labels = None
depends_on = None

CHECKS = {
    "ck_jobs_salary_currency": "salary_currency IS NULL OR salary_currency ~ '^[A-Z]{3}$'",
    "ck_jobs_salary_period": "salary_period IS NULL OR salary_period IN ('year', 'month')",
}
TITLE_KEY = r"lower(regexp_replace(btrim(title), '\s+', ' ', 'g'))"
INDEX = "ix_jobs_company_title_key"
FOREIGN_KEYS = {"fk_jobs_lead_source_id": ("lead_source_id", "rec_lead_sources"), "fk_jobs_hiring_manager": ("hiring_manager_user_id", "users"),
                "fk_jobs_updated_by": ("updated_by_user_id", "users")}  # fmt: skip


def _columns() -> list[sa.Column]:
    return [
        sa.Column("requisition_reference", sa.String(80), nullable=True),
        sa.Column("lead_source_id", sa.Uuid(), nullable=True),
        sa.Column("certifications", sa.String(1000), nullable=True),
        sa.Column("country", sa.String(120), nullable=True),
        sa.Column("state", sa.String(120), nullable=True),
        sa.Column("city", sa.String(120), nullable=True),
        sa.Column("relocation_required", sa.Boolean(), nullable=True),
        sa.Column("travel_requirement", sa.String(120), nullable=True),
        sa.Column("salary_currency", sa.String(3), nullable=True),
        sa.Column("salary_period", sa.String(5), nullable=True),
        sa.Column("benefits", sa.String(1000), nullable=True),
        sa.Column("hiring_manager_user_id", sa.Uuid(), nullable=True),
        sa.Column("expected_joining_date", sa.Date(), nullable=True),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
    ]


def upgrade() -> None:
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(op.get_bind())
    existing = set() if offline else {c["name"] for c in inspector.get_columns("jobs")}
    added = set()
    for column in _columns():
        if column.name not in existing:
            op.add_column("jobs", column)
            added.add(column.name)
    for name, (column, table) in FOREIGN_KEYS.items():
        if offline or column in added:
            op.create_foreign_key(name, "jobs", table, [column], ["id"])
    checks = set() if offline else {c["name"] for c in inspector.get_check_constraints("jobs")}
    for name, sql in CHECKS.items():
        if name not in checks:
            op.create_check_constraint(name, "jobs", sql)
    if offline or INDEX not in {i["name"] for i in inspector.get_indexes("jobs")}:
        op.create_index(INDEX, "jobs", ["company_id", sa.text(TITLE_KEY)])


def downgrade() -> None:
    op.drop_index(INDEX, table_name="jobs", if_exists=True)
    for name in CHECKS:
        op.execute(f"ALTER TABLE jobs DROP CONSTRAINT IF EXISTS {name}")
    for column in reversed(_columns()):
        op.execute(f"ALTER TABLE jobs DROP COLUMN IF EXISTS {column.name}")  # drops its foreign key too
