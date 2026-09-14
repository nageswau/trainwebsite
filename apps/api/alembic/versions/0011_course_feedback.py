"""Add course_feedback (STU-008, DATA_MODEL.md §4.6 correction).

Revision ID: 0011_course_feedback
Revises: 0010_support_ticket_assignment

DATA_MODEL.md §4.6 describes `CourseFeedback` as "carries over" from the reference
implementation. Building STU-008 found no such table (or any other feedback model)
anywhere in the codebase -- same "doc says X carries over but it never existed" pattern
already corrected once for STU-005's `assigned_to_user_id`. Net-new table.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011_course_feedback"
down_revision = "0010_support_ticket_assignment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = inspector.get_table_names()

    if "course_feedback" not in existing:
        op.create_table(
            "course_feedback",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("batch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("batches.id"), nullable=False),
            sa.Column("rating", sa.Integer, nullable=False),
            sa.Column("comments", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_course_feedback_student_id", "course_feedback", ["student_id"])
        op.create_index("ix_course_feedback_batch_id", "course_feedback", ["batch_id"])


def downgrade() -> None:
    op.drop_index("ix_course_feedback_batch_id", table_name="course_feedback")
    op.drop_index("ix_course_feedback_student_id", table_name="course_feedback")
    op.drop_table("course_feedback")
