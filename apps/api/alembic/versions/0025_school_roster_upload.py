"""Add school_roster_upload_batches, school_roster_upload_rows (SCH-002).

Revision ID: 0025_school_roster_upload
Revises: 0024_school_students_activities

`DATA_MODEL.md` §6.13. Net-new -- bulk-upload audit trail: a batch-level summary row plus
one row-level accept/reject record per uploaded row, so `accepted_count + rejected_count`
is always reconstructable and every accepted row traces to the `SchoolStudent` it created
(`SCH-002-AC04`'s partial-batch-integrity requirement).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0025_school_roster_upload"
down_revision = "0024_school_students_activities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = inspector.get_table_names()

    if "school_roster_upload_batches" not in existing:
        op.create_table(
            "school_roster_upload_batches",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("school_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("schools.id"), nullable=False),
            sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("idempotency_key", sa.String(120), nullable=False),
            sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("accepted_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("rejected_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(20), nullable=False, server_default="processing"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_school_roster_upload_batches_school_id", "school_roster_upload_batches", ["school_id"])
        op.create_index("ix_school_roster_upload_batches_idempotency_key", "school_roster_upload_batches", ["idempotency_key"], unique=True)

    if "school_roster_upload_rows" not in existing:
        op.create_table(
            "school_roster_upload_rows",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("batch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("school_roster_upload_batches.id"), nullable=False),
            sa.Column("row_number", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("school_students.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_school_roster_upload_rows_batch_id", "school_roster_upload_rows", ["batch_id"])


def downgrade() -> None:
    op.drop_table("school_roster_upload_rows")
    op.drop_table("school_roster_upload_batches")
