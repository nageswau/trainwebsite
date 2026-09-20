"""ENH-004 -- school_student_grade_history (append-only promotion/hold-back ledger).

Revision ID: 0033_student_grade_history
Revises: 0032_welcome_token_purpose

docs/superpowers/specs/2026-09-19-enh-004-student-promotion-design.md §5.1. Create-table only:
no existing table is altered and no existing row is read or written (each history row carries its
own "from" state, so there is nothing to backfill). `downgrade()` drops only this table.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0033_student_grade_history"
down_revision = "0032_welcome_token_purpose"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "school_student_grade_history" in inspector.get_table_names():
        return
    op.create_table(
        "school_student_grade_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("school_student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("school_students.id"), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("from_academic_year_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("academic_years.id"), nullable=True),
        sa.Column("from_grade_level", sa.Integer(), nullable=True),
        sa.Column("from_grade_or_class", sa.String(60), nullable=True),
        sa.Column("to_academic_year_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("academic_years.id"), nullable=False),
        sa.Column("to_grade_level", sa.Integer(), nullable=True),
        sa.Column("to_grade_or_class", sa.String(60), nullable=True),
        sa.Column("performed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("school_student_id", "to_academic_year_id", name="uq_school_student_grade_history_year"),
    )
    op.create_index("ix_school_student_grade_history_school_student_id", "school_student_grade_history", ["school_student_id"])


def downgrade() -> None:
    op.drop_index("ix_school_student_grade_history_school_student_id", table_name="school_student_grade_history")
    op.drop_table("school_student_grade_history")
