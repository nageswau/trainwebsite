"""ENH-020 -- school_funding_records.

Revision ID: 0051_school_funding_records
Revises: 0050_notification_channels

docs/superpowers/specs/2026-10-01-enh-020-funding-support-tracking-design.md §3.1 (DEC-SCOPE-043). Create-table only: no existing
table is altered and no existing row is read or written. Guarded like 0048: on a fresh database 0001_initial's create_all() has
already built the table from the model. `downgrade()` drops the table and its indexes. Renumber on merge if `main` takes 0051 first.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0051_school_funding_records"
down_revision = "0050_notification_channels"
branch_labels = None
depends_on = None

TABLE = "school_funding_records"


def upgrade() -> None:
    if not op.get_context().as_sql and TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("school_student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("school_students.id"), nullable=False),
        sa.Column("school_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("schools.id"), nullable=False),
        sa.Column("support_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("status_changed_on", sa.Date(), nullable=False),
        sa.Column("provider_name", sa.String(200), nullable=True),
        sa.Column("amount_text", sa.String(120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("closure_reason", sa.String(500), nullable=True),
        sa.Column("career_counselor_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("support_type IN ('education_loan', 'financial_assistance', 'scholarship', 'funding_guidance')", name="ck_funding_record_support_type"),
        sa.CheckConstraint("status IN ('required', 'counselling', 'documents', 'application', 'approved', 'completed', 'closed')", name="ck_funding_record_status"),
        sa.CheckConstraint("(status = 'closed') = (closure_reason IS NOT NULL)", name="ck_funding_record_closure"),
    )
    op.create_index("ix_school_funding_records_school_student_id", TABLE, ["school_student_id"])
    op.create_index("ix_school_funding_records_school_type", TABLE, ["school_id", "support_type"])
    op.create_index("uq_funding_record_open_student_type", TABLE, ["school_student_id", "school_id", "support_type"], unique=True, postgresql_where=sa.text("status NOT IN ('completed', 'closed')"))


def downgrade() -> None:
    op.drop_table(TABLE)
