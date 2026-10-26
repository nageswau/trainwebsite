"""nehn-024 -- the submission_files link between an assignment submission and its uploaded stored_files.

Revision ID: 0200_submission_files
Revises: 0199_audit_log_indexes

docs/superpowers/specs/2026-10-26-nehn-024-submission-file-upload-design.md (DEC-SCOPE-291 F1). 0001 builds a fresh database from the
current models, which already carry the table, so it is created only when missing (0194's idiom). No existing row changes;
`submissions.file_url` stays. The downgrade drops the links; the submissions and stored files stay.
"""

import sqlalchemy as sa

from alembic import op

revision = "0200_submission_files"
down_revision = "0199_audit_log_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    offline = op.get_context().as_sql
    if offline or "submission_files" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "submission_files",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("submission_id", sa.Uuid(), sa.ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("stored_file_id", sa.Uuid(), sa.ForeignKey("stored_files.id", ondelete="CASCADE"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("stored_file_id", name="uq_submission_files_stored_file"),
        )
        op.create_index("ix_submission_files_submission_id", "submission_files", ["submission_id"])


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS submission_files")
