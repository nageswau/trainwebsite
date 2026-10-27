"""nehn-027 -- an uploaded file, an order and a soft delete for trainer learning materials.

Revision ID: 0202_learning_resource_files
Revises: 0201_coordinator_role

docs/superpowers/specs/2026-10-27-nehn-027-learning-material-files-design.md (DEC-SCOPE-294 M1). `learning_resources` gains
`stored_file_id` (unique, SET NULL when the stored file goes), `sort_order` (0) and `deleted_at`; `url` becomes nullable because a file
resource has none. Each step runs only when missing (0001 builds a fresh database from the current models; 0197's idiom). Existing rows
keep their `url` and get `sort_order` 0. The downgrade drops the rows a trainer already deleted, points each file resource at its owner
route (`/api/v1/files/{id}`, nehn-003) so `url` can be NOT NULL again, then drops the columns.
"""

import sqlalchemy as sa

from alembic import op

revision = "0202_learning_resource_files"
down_revision = "0201_coordinator_role"
branch_labels = None
depends_on = None

TABLE = "learning_resources"
UNIQUE = "uq_learning_resources_stored_file"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {c["name"]: c for c in inspector.get_columns(TABLE)}
    if "stored_file_id" not in columns:
        op.add_column(TABLE, sa.Column("stored_file_id", sa.Uuid(), sa.ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True))
    if UNIQUE not in {c["name"] for c in inspector.get_unique_constraints(TABLE)}:
        op.create_unique_constraint(UNIQUE, TABLE, ["stored_file_id"])
    if "sort_order" not in columns:
        op.add_column(TABLE, sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"))
    if "deleted_at" not in columns:
        op.add_column(TABLE, sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    if not columns["url"]["nullable"]:
        op.alter_column(TABLE, "url", existing_type=sa.String(500), nullable=True)


def downgrade() -> None:
    op.execute(f"DELETE FROM {TABLE} WHERE deleted_at IS NOT NULL")
    op.execute(f"UPDATE {TABLE} SET url = '/api/v1/files/' || stored_file_id::text WHERE url IS NULL AND stored_file_id IS NOT NULL")
    op.execute(f"DELETE FROM {TABLE} WHERE url IS NULL")  # a file resource whose stored file is already gone has nothing to point at
    op.alter_column(TABLE, "url", existing_type=sa.String(500), nullable=False)
    op.drop_column(TABLE, "deleted_at")
    op.drop_column(TABLE, "sort_order")
    op.drop_column(TABLE, "stored_file_id")  # drops its unique constraint and FK with it
