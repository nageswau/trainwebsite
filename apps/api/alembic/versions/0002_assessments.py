"""Add trainer assessments.

Revision ID: 0002_assessments
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_assessments"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if "assessments" in inspector.get_table_names():
        return
    op.create_table(
        "assessments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("batches.id"), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("max_score", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("status", sa.String(30), nullable=False, server_default="scheduled"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_assessments_batch_id", "assessments", ["batch_id"])


def downgrade():
    op.drop_index("ix_assessments_batch_id", table_name="assessments")
    op.drop_table("assessments")
