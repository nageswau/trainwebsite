"""Add profile_documents (STU-011).

Revision ID: 0012_profile_documents
Revises: 0011_course_feedback

DATA_MODEL.md names no table at all for STU-011. The existing `StudentDocument` table is
Overseas-division-specific (FK to `overseas_applications`, gated to overseas roles) and
not reusable for an IT student's own CV/portfolio uploads without conflating two
different domains. Net-new table.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0012_profile_documents"
down_revision = "0011_course_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = inspector.get_table_names()

    if "profile_documents" not in existing:
        op.create_table(
            "profile_documents",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("document_type", sa.String(80), nullable=False),
            sa.Column("file_url", sa.String(500), nullable=False),
            sa.Column("original_filename", sa.String(255), nullable=True),
            sa.Column("content_type", sa.String(120), nullable=True),
            sa.Column("file_size", sa.Integer, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_profile_documents_user_id", "profile_documents", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_profile_documents_user_id", table_name="profile_documents")
    op.drop_table("profile_documents")
