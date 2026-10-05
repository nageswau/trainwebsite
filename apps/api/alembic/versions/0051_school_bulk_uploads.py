"""ENH-028 -- school_bulk_upload_batches / school_bulk_upload_rows.

Revision ID: 0051_school_bulk_uploads
Revises: 0050_notification_channels

docs/superpowers/specs/2026-10-01-enh-028-bulk-data-entry-design.md §4 (DEC-SCOPE-043). Create-table only: no existing table is
altered and no existing row is read or written. Cut as 0049; renumbered to 0051 after AGN-004's 0049 and ENH-014's 0050 on merging main. `downgrade()` drops both tables (rows first, for the foreign key).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0051_school_bulk_uploads"
down_revision = "0050_notification_channels"
branch_labels = None
depends_on = None

BATCHES = "school_bulk_upload_batches"
ROWS = "school_bulk_upload_rows"


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    if not op.get_context().as_sql and BATCHES in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        BATCHES,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("target_type", sa.String(30), nullable=False),
        sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("accepted_count", sa.Integer(), nullable=False),
        sa.Column("rejected_count", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("uploaded_by_user_id", "target_type", "idempotency_key", name="uq_school_bulk_upload_key"),
        sa.CheckConstraint(
            "target_type IN ('academic_result', 'psychometric_record', 'test_prep_record', 'language_record')",
            name="ck_school_bulk_upload_target_type",
        ),
    )
    op.create_table(
        ROWS,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey(f"{BATCHES}.id"), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("student_code", sa.String(8), nullable=True),
        sa.Column("created_record_id", postgresql.UUID(as_uuid=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("status IN ('accepted', 'rejected')", name="ck_school_bulk_upload_row_status"),
    )
    op.create_index("ix_school_bulk_upload_rows_batch_id", ROWS, ["batch_id"])


def downgrade() -> None:
    op.drop_table(ROWS)
    op.drop_table(BATCHES)
