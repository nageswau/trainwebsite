"""ENH-018 -- school_activity_feedback.

Revision ID: 0040_school_activity_feedback
Revises: 0039_student_career_goal

docs/superpowers/specs/2026-09-23-enh-018-school-activity-feedback-design.md §4. Create-table only: no existing
table is altered and no existing row is read or written. `downgrade()` drops the table.

Re-chained on merge with `main`, 2026-09-23: originally cut as `0039_school_activity_feedback` on top of `0038_portfolio`,
the same parent ENH-013's `0039_student_career_goal` used independently. Renumbered past it, leaving a single alembic head
(the ENH-009/011/012 collision-and-renumber precedent recorded in `docs/quality/RTM.md`).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0040_school_activity_feedback"
down_revision = "0039_student_career_goal"
branch_labels = None
depends_on = None

TABLE = "school_activity_feedback"


def upgrade() -> None:
    if not op.get_context().as_sql and TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("activity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("school_activities.id"), nullable=False),
        sa.Column("school_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("schools.id"), nullable=False),
        sa.Column("submitted_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("trainer_name", sa.String(200), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("satisfaction", sa.Integer(), nullable=False),
        sa.Column("feedback", sa.Text(), nullable=False),
        sa.Column("suggestions", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("activity_id", name="uq_activity_feedback_activity"),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_activity_feedback_rating"),
        sa.CheckConstraint("satisfaction BETWEEN 1 AND 5", name="ck_activity_feedback_satisfaction"),
    )
    op.create_index("ix_school_activity_feedback_school_id", TABLE, ["school_id"])
    op.create_index("ix_school_activity_feedback_created_at", TABLE, ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_school_activity_feedback_created_at", table_name=TABLE)
    op.drop_index("ix_school_activity_feedback_school_id", table_name=TABLE)
    op.drop_table(TABLE)
