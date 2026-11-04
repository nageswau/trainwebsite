"""hrc-013 -- candidate bulk import: the `candidate_import_batches` and `candidate_import_rows` tables and the default `candidates.import`
grant (recruiters and placement managers).

Revision ID: 0268_candidate_imports
Revises: 0267_application_review

docs/superpowers/specs/2026-11-04-hrc-013-candidate-bulk-import-design.md (DEC-SCOPE-391). Two new tables; 0001 builds a fresh database
from the current models, which already carry them, so each runs only when missing (0256's idiom). The checks and SEED are frozen copies of
the model / `rbac` at this revision. The downgrade drops both tables and the `candidates.import` grant rows (with their overrides); no
candidate changes.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0268_candidate_imports"
down_revision = "0267_application_review"
branch_labels = None
depends_on = None

BATCH_CHECKS = {"ck_candidate_import_batches_counts": "created_count + matched_count + error_count = total_rows"}
ROW_CHECKS = {
    "ck_candidate_import_rows_status": "status IN ('created', 'matched', 'error')",
    "ck_candidate_import_rows_outcome": "(status = 'error') = (candidate_id IS NULL) AND (status <> 'error' OR reason IS NOT NULL)",
}
SEED = (("placement_team", "candidates", "import"), ("placement_manager", "candidates", "import"))
UUID = postgresql.UUID(as_uuid=True)


def _count(name: str) -> sa.Column:
    return sa.Column(name, sa.Integer(), server_default=sa.text("0"), nullable=False)


def upgrade() -> None:
    offline = op.get_context().as_sql
    tables = set() if offline else set(sa.inspect(op.get_bind()).get_table_names())
    if "candidate_import_batches" not in tables:
        op.create_table(
            "candidate_import_batches",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("uploaded_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("source_id", UUID, sa.ForeignKey("rec_candidate_sources.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("idempotency_key", sa.String(120), nullable=False),
            sa.Column("file_sha256", sa.String(64), nullable=False),
            sa.Column("file_name", sa.String(200), nullable=False),
            _count("total_rows"),
            _count("created_count"),
            _count("matched_count"),
            _count("error_count"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("uploaded_by_user_id", "idempotency_key", name="uq_candidate_import_batches_key"),
            *(sa.CheckConstraint(sql, name=name) for name, sql in BATCH_CHECKS.items()),
        )
        op.create_index("ix_candidate_import_batches_uploader", "candidate_import_batches", ["uploaded_by_user_id", "created_at"])
        op.create_index("ix_candidate_import_batches_file", "candidate_import_batches", ["uploaded_by_user_id", "file_sha256"])
    if "candidate_import_rows" not in tables:
        op.create_table(
            "candidate_import_rows",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("batch_id", UUID, sa.ForeignKey("candidate_import_batches.id", ondelete="CASCADE"), nullable=False),
            sa.Column("row_number", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(10), nullable=False),
            sa.Column("candidate_id", UUID, sa.ForeignKey("candidates.id", ondelete="RESTRICT"), nullable=True),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.UniqueConstraint("batch_id", "row_number", name="uq_candidate_import_rows_row"),
            *(sa.CheckConstraint(sql, name=name) for name, sql in ROW_CHECKS.items()),
        )
        op.create_index("ix_candidate_import_rows_candidate", "candidate_import_rows", ["candidate_id"])
    for role, resource, action in SEED:
        op.execute(sa.text("INSERT INTO role_permissions (role, resource, action) VALUES (:role, :resource, :action) ON CONFLICT DO NOTHING").bindparams(role=role, resource=resource, action=action))


def downgrade() -> None:
    # only `import`: hrc-002 declared the same resource's export/merge keys, which other items own
    op.execute("DELETE FROM user_permission_overrides WHERE resource = 'candidates' AND action = 'import'")
    op.execute("DELETE FROM role_permissions WHERE resource = 'candidates' AND action = 'import'")
    op.drop_table("candidate_import_rows")
    op.drop_table("candidate_import_batches")
