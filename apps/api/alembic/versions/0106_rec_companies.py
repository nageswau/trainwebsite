"""rec-003 -- the company master: recruiter lead columns on `companies`, the CMP- code (with backfill) and company_assignment_history.

Revision ID: 0106_rec_companies
Revises: 0105_university_master

docs/superpowers/specs/2026-10-08-rec-003-company-master-design.md §3 (DEC-SCOPE-121). Every new `companies` column is nullable except
`company_code`, which existing rows get in `created_at`, `id` order before NOT NULL is set; new rows get it from the server default, so
no insert path (EMP-001, /workflows/it/jobs) changes. Drafted as 0103_rec_companies after 0102_rec_catalogues; upc-001's 0103, rec-006's 0104 and upc-003's 0105_university_master
reached main first, so this is 0106. A database stamped at an earlier rec_companies revision is re-stamped with `alembic stamp --purge
0102_rec_catalogues` then `upgrade head` (every create here is guarded).
0001 builds a fresh database from the current models, which already carry all of
this, so every object is created only when missing (0069's idiom). downgrade() refuses while recruiter company data exists (any history
row or any value in a new column other than the code): entered data is never dropped silently.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0106_rec_companies"
down_revision = "0105_university_master"
branch_labels = None
depends_on = None

TABLE = "companies"
HISTORY = "company_assignment_history"
SEQ = "company_code_seq"
CODE_DEFAULT = f"'CMP-' || lpad(nextval('{SEQ}')::text, 6, '0')"
UUID = postgresql.UUID(as_uuid=True)
COLUMNS = (
    ("linkedin_url", sa.String(300), None),
    ("industry_id", UUID, "rec_industries"),
    ("company_size_id", UUID, "rec_company_sizes"),
    ("employee_count", sa.Integer(), None),
    ("city", sa.String(120), None),
    ("state", sa.String(120), None),
    ("country", sa.String(120), None),
    ("head_office", sa.String(300), None),
    ("branches", sa.String(1000), None),
    ("description", sa.String(2000), None),
    ("lead_source_id", UUID, "rec_lead_sources"),
    ("campaign_id", UUID, "rec_campaigns"),
    ("priority", sa.String(10), None),
    ("assigned_recruiter_user_id", UUID, "users"),
    ("assigned_bdm_user_id", UUID, "users"),
    ("created_by_user_id", UUID, "users"),
    ("archived_at", sa.DateTime(timezone=True), None),
)
CHECKS = {  # must equal app.models.COMPANY_CHECKS (test_rec_003_migration)
    "ck_companies_priority": "priority IS NULL OR priority IN ('hot', 'warm', 'cold')",
    "ck_companies_employee_count": "employee_count IS NULL OR employee_count BETWEEN 0 AND 10000000",
}
INDEXES = {
    "ix_companies_assigned_recruiter": ["assigned_recruiter_user_id"],
    "ix_companies_assigned_bdm": ["assigned_bdm_user_id"],
    "ix_companies_name_key": [sa.text(r"lower(regexp_replace(btrim(name), '\s+', ' ', 'g'))")],
}
# Row numbers fix the order (the oldest company is CMP-000001); the sequence then continues after the last backfilled code.
BACKFILL = f"UPDATE {TABLE} c SET company_code = 'CMP-' || lpad(o.n::text, 6, '0') FROM (SELECT id, row_number() OVER (ORDER BY created_at, id) AS n FROM {TABLE}) o WHERE c.id = o.id"
ADVANCE = f"SELECT setval('{SEQ}', (SELECT count(*) FROM {TABLE})) WHERE EXISTS (SELECT 1 FROM {TABLE})"


def _inspect():
    return None if op.get_context().as_sql else sa.inspect(op.get_bind())  # offline SQL: emit everything


def upgrade() -> None:
    inspector = _inspect()
    columns = {c["name"] for c in inspector.get_columns(TABLE)} if inspector else set()
    checks = {c["name"] for c in inspector.get_check_constraints(TABLE)} if inspector else set()
    indexes = {i["name"] for i in inspector.get_indexes(TABLE)} if inspector else set()
    uniques = {u["name"] for u in inspector.get_unique_constraints(TABLE)} if inspector else set()
    op.execute(f"CREATE SEQUENCE IF NOT EXISTS {SEQ} MAXVALUE 999999")
    if "company_code" not in columns:
        op.add_column(TABLE, sa.Column("company_code", sa.String(20), nullable=True))
        op.execute(BACKFILL)
        op.execute(ADVANCE)
        op.alter_column(TABLE, "company_code", nullable=False, server_default=sa.text(CODE_DEFAULT))
    if "uq_companies_code" not in uniques:
        op.create_unique_constraint("uq_companies_code", TABLE, ["company_code"])
    for name, type_, target in COLUMNS:
        if name not in columns:
            fk = [sa.ForeignKey(f"{target}.id")] if target else []
            op.add_column(TABLE, sa.Column(name, type_, *fk, nullable=True))
    for name, sql in CHECKS.items():
        if name not in checks:
            op.create_check_constraint(name, TABLE, sql)
    for name, cols in INDEXES.items():
        if name not in indexes:
            op.create_index(name, TABLE, cols)
    if inspector is None or HISTORY not in inspector.get_table_names():
        op.create_table(
            HISTORY,
            sa.Column("id", UUID, primary_key=True),
            sa.Column("company_id", UUID, sa.ForeignKey("companies.id"), nullable=False),
            sa.Column("from_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
            sa.Column("to_user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("changed_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_company_assignment_history_company", HISTORY, ["company_id"])


def downgrade() -> None:
    if not op.get_context().as_sql:
        filled = " OR ".join(f"{name} IS NOT NULL" for name, _, _ in COLUMNS)
        bind = op.get_bind()
        if bind.execute(sa.text(f"SELECT 1 FROM {HISTORY} LIMIT 1")).first() or bind.execute(sa.text(f"SELECT 1 FROM {TABLE} WHERE {filled} LIMIT 1")).first():
            raise RuntimeError("Cannot downgrade 0106_rec_companies: recruiter company data exists. Clear it deliberately first.")
    op.drop_table(HISTORY)
    for name in INDEXES:
        op.drop_index(name, table_name=TABLE)
    for name in CHECKS:
        op.drop_constraint(name, TABLE, type_="check")
    for name, _, _ in reversed(COLUMNS):
        op.drop_column(TABLE, name)
    op.drop_constraint("uq_companies_code", TABLE, type_="unique")
    op.drop_column(TABLE, "company_code")
    op.execute(f"DROP SEQUENCE IF EXISTS {SEQ}")
