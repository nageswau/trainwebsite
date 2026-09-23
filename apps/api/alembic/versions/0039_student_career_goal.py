"""ENH-013 -- school_students.career_goal.

Revision ID: 0039_student_career_goal
Revises: 0038_portfolio

docs/superpowers/specs/2026-09-23-enh-013a-student-360-view-design.md §5. Add-column only: nullable, no default, no
backfill, so no existing row is read or rewritten (a metadata-only change on PostgreSQL). `downgrade()` drops the column.
"""

import sqlalchemy as sa

from alembic import op

revision = "0039_student_career_goal"
down_revision = "0038_portfolio"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("school_students", sa.Column("career_goal", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("school_students", "career_goal")
