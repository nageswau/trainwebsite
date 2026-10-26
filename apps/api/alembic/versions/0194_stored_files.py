"""nehn-003 -- the stored_files metadata table behind `POST /files/upload` and `GET /files/{id}`.

Revision ID: 0194_stored_files
Revises: 0193_student_archive_consent

docs/superpowers/specs/2026-10-26-nehn-003-private-storage-design.md (DEC-SCOPE-279 PS5). 0001 builds a fresh database from the current
models, which already carry the table, so it is created only when missing (0192's idiom). No existing row changes. The downgrade drops
the table; the objects themselves stay in storage.
"""

import sqlalchemy as sa

from alembic import op

revision = "0194_stored_files"
down_revision = "0193_student_archive_consent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    offline = op.get_context().as_sql
    if offline or "stored_files" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "stored_files",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("key", sa.String(500), nullable=False),
            sa.Column("purpose", sa.String(40), nullable=False),
            sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("original_filename", sa.String(255), nullable=False),
            sa.Column("content_type", sa.String(120), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=False),
            sa.Column("sha256", sa.String(64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("key", name="uq_stored_files_key"),
        )
        op.create_index("ix_stored_files_owner_id", "stored_files", ["owner_id"])


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS stored_files")
