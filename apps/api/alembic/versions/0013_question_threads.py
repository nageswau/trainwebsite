"""Add question_threads, question_replies (TRN-009).

Revision ID: 0013_question_threads
Revises: 0012_profile_documents

DATA_MODEL.md §4.8 describes `QuestionThread`/`QuestionReply` as "carries over" from the
reference implementation. Building TRN-009 found neither table -- nor any Q&A model --
anywhere in the codebase, the same "carries over but never existed" pattern already
corrected for STU-005 and STU-008. Both tables are net-new.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0013_question_threads"
down_revision = "0012_profile_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = inspector.get_table_names()

    if "question_threads" not in existing:
        op.create_table(
            "question_threads",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("batch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("batches.id"), nullable=False),
            sa.Column("subject", sa.String(180), nullable=False),
            sa.Column("body", sa.Text, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_question_threads_student_id", "question_threads", ["student_id"])
        op.create_index("ix_question_threads_batch_id", "question_threads", ["batch_id"])

    if "question_replies" not in existing:
        op.create_table(
            "question_replies",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("thread_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("question_threads.id", ondelete="CASCADE"), nullable=False),
            sa.Column("author_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("body", sa.Text, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_question_replies_thread_id", "question_replies", ["thread_id"])


def downgrade() -> None:
    op.drop_index("ix_question_replies_thread_id", table_name="question_replies")
    op.drop_table("question_replies")
    op.drop_index("ix_question_threads_batch_id", table_name="question_threads")
    op.drop_index("ix_question_threads_student_id", table_name="question_threads")
    op.drop_table("question_threads")
