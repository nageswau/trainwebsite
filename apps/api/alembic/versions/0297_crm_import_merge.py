"""pob-006 -- company and contact import, and authorised merge: `merged_into_id`, `merged_at`, `merged_by_user_id` on `companies` and
`company_contacts`, the `crm_import_batches` and `crm_import_rows` tables and the default `crm.import` / `crm.merge` grants (placement managers).

Revision ID: 0297_crm_import_merge
Revises: 0295_recruitment_report_grants

docs/superpowers/specs/2026-11-06-pob-006-company-import-merge-design.md (DEC-SCOPE-418). 0001 builds a fresh database from the current models, which already
carry all of this, so each step runs only when missing (0256's idiom). The checks and SEED are frozen copies of the models / `rbac` at this revision. The
upgrade changes no existing row. The downgrade drops the tables, the columns and the grant rows (with their overrides).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0297_crm_import_merge"
down_revision = "0295_recruitment_report_grants"
branch_labels = None
depends_on = None

BATCH_CHECKS = {"ck_crm_import_batches_counts": "created_count + matched_count + error_count = total_rows"}
ROW_CHECKS = {
    "ck_crm_import_rows_status": "status IN ('created', 'matched', 'error')",
    "ck_crm_import_rows_outcome": "(status <> 'created' OR company_id IS NOT NULL) AND (status = 'created' OR reason IS NOT NULL)",
}
SEED = (("placement_manager", "crm", "import"), ("placement_manager", "crm", "merge"))
UUID = postgresql.UUID(as_uuid=True)
MERGEABLE = {"companies": "ck_companies_merged_not_self", "company_contacts": "ck_company_contacts_merged_not_self"}
NOT_SELF = "merged_into_id IS NULL OR merged_into_id <> id"


def _count(name: str) -> sa.Column:
    return sa.Column(name, sa.Integer(), server_default=sa.text("0"), nullable=False)


def _add_merge_columns(inspector, offline: bool) -> None:
    for table, check in MERGEABLE.items():
        have = set() if offline else {c["name"] for c in inspector.get_columns(table)}
        if "merged_into_id" not in have:
            op.add_column(table, sa.Column("merged_into_id", UUID, sa.ForeignKey(f"{table}.id", ondelete="RESTRICT", name=f"fk_{table}_merged_into"), nullable=True))
        if "merged_at" not in have:
            op.add_column(table, sa.Column("merged_at", sa.DateTime(timezone=True), nullable=True))
        if "merged_by_user_id" not in have:
            op.add_column(table, sa.Column("merged_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT", name=f"fk_{table}_merged_by"), nullable=True))
        checks = set() if offline else {c["name"] for c in inspector.get_check_constraints(table)}
        if check not in checks:
            op.create_check_constraint(check, table, NOT_SELF)


def upgrade() -> None:
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(op.get_bind())
    _add_merge_columns(inspector, offline)
    tables = set() if offline else set(inspector.get_table_names())
    if "crm_import_batches" not in tables:
        op.create_table(
            "crm_import_batches",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("uploaded_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("idempotency_key", sa.String(120), nullable=False),
            sa.Column("file_sha256", sa.String(64), nullable=False),
            sa.Column("file_name", sa.String(200), nullable=False),
            _count("total_rows"),
            _count("created_count"),
            _count("matched_count"),
            _count("error_count"),
            _count("companies_created"),
            _count("contacts_created"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("uploaded_by_user_id", "idempotency_key", name="uq_crm_import_batches_key"),
            *(sa.CheckConstraint(sql, name=name) for name, sql in BATCH_CHECKS.items()),
        )
        op.create_index("ix_crm_import_batches_uploader", "crm_import_batches", ["uploaded_by_user_id", "created_at"])
        op.create_index("ix_crm_import_batches_file", "crm_import_batches", ["uploaded_by_user_id", "file_sha256"])
    if "crm_import_rows" not in tables:
        op.create_table(
            "crm_import_rows",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("batch_id", UUID, sa.ForeignKey("crm_import_batches.id", ondelete="CASCADE"), nullable=False),
            sa.Column("row_number", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(10), nullable=False),
            sa.Column("company_id", UUID, sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=True),
            sa.Column("contact_id", UUID, sa.ForeignKey("company_contacts.id", ondelete="RESTRICT"), nullable=True),
            sa.Column("company_created", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("contact_created", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.UniqueConstraint("batch_id", "row_number", name="uq_crm_import_rows_row"),
            *(sa.CheckConstraint(sql, name=name) for name, sql in ROW_CHECKS.items()),
        )
        op.create_index("ix_crm_import_rows_company", "crm_import_rows", ["company_id"])
        op.create_index("ix_crm_import_rows_contact", "crm_import_rows", ["contact_id"])
    for role, resource, action in SEED:
        op.execute(sa.text("INSERT INTO role_permissions (role, resource, action) VALUES (:role, :resource, :action) ON CONFLICT DO NOTHING").bindparams(role=role, resource=resource, action=action))


def downgrade() -> None:
    op.execute("DELETE FROM user_permission_overrides WHERE resource = 'crm'")
    op.execute("DELETE FROM role_permissions WHERE resource = 'crm'")
    op.drop_table("crm_import_rows")
    op.drop_table("crm_import_batches")
    for table, check in MERGEABLE.items():
        op.drop_constraint(check, table, type_="check")
        for column in ("merged_by_user_id", "merged_at", "merged_into_id"):
            op.drop_column(table, column)
