"""upc-005 -- University CSV import batches.

Revision ID: 0112_university_imports
Revises: 0111_university_pipeline

docs/superpowers/specs/2026-10-08-upc-005-university-import-design.md §2 (DEC-SCOPE-127). Adds `university_import_batches`: one row per
import with the file hash, the counts and each row's outcome (never the file). 0001 builds a fresh database from the current models, which
already carry this table, so the create is guarded. COUNTS_SQL repeats app.models (test_upc_005_migration). downgrade() refuses while any
batch exists: it would drop the import history.

Drafted as `0110_university_imports` on `0109_university_duplicates` and re-chained on merging `main` @ `f5f6822d`: rec-004 took `DEC-SCOPE-125` / `0110` / §12AS / §2.51 and upc-007 took `DEC-SCOPE-126` / `0111` / §12AT / §2.52.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0112_university_imports"
down_revision = "0111_university_pipeline"
branch_labels = None
depends_on = None

TABLE = "university_import_batches"
KEY_UNIQUE = "uq_university_import_batches_key"
UPLOADER_INDEX = "ix_university_import_batches_uploader"
COUNTS_CHECK = "ck_university_import_batches_counts"
COUNTS_SQL = "created_count + duplicate_count + invalid_count = total_rows"
UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    if not op.get_context().as_sql and TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        TABLE,
        sa.Column("id", UUID, primary_key=True),
        sa.Column("uploaded_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        *(sa.Column(name, sa.Integer(), nullable=False, server_default=sa.text("0")) for name in ("total_rows", "created_count", "duplicate_count", "invalid_count")),
        sa.Column("results_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("uploaded_by_user_id", "idempotency_key", name=KEY_UNIQUE),
        sa.CheckConstraint(COUNTS_SQL, name=COUNTS_CHECK),
    )
    op.create_index(UPLOADER_INDEX, TABLE, ["uploaded_by_user_id", "created_at"])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0112_university_imports: university import history exists. Remove it deliberately first.")
    op.drop_table(TABLE)
