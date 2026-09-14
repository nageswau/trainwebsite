"""Add submissions.is_late (STU-004-AC02, DATA_MODEL.md §4.2).

Revision ID: 0007_submission_is_late
Revises: 0006_public_content_collections

STU-004's own error/edge requirement: "Submission after due date flagged, not silently
accepted unless allowed." The base codebase's submission endpoint never computed or
stored this at all. Additive column, backfilled from existing rows' own created_at vs.
their assignment's due_date so historical data isn't left inconsistent with new rows.
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_submission_is_late"
down_revision = "0006_public_content_collections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {c["name"] for c in inspector.get_columns("submissions")} if "submissions" in inspector.get_table_names() else set()
    if "is_late" not in columns:
        op.add_column("submissions", sa.Column("is_late", sa.Boolean, nullable=False, server_default=sa.false()))
        op.execute(
            "UPDATE submissions AS s SET is_late = true "
            "FROM assignments AS a WHERE a.id = s.assignment_id AND s.created_at > a.due_date"
        )


def downgrade() -> None:
    op.drop_column("submissions", "is_late")
