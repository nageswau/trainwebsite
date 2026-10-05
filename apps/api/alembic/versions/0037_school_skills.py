"""ENH-011 -- school skills tracker: Soft Skills / Digital Skills batches, enrolments, sessions, attendance, assessments, scores.

Revision ID: 0035_school_skills
Revises: 0034_school_transfer_requests

docs/superpowers/specs/2026-09-22-enh-011-skills-tracker-design.md §4. Create-table only: no existing table is altered and
no existing row is read or written, so there is nothing to backfill. `downgrade()` drops only these six tables, children
first.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0037_school_skills"
down_revision = "0036_backfill_school_code"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
TABLES = ["school_skill_batches", "school_skill_enrollments", "school_skill_sessions", "school_skill_attendance", "school_skill_assessments", "school_skill_scores"]


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def _user(name: str) -> sa.Column:
    return sa.Column(name, UUID, sa.ForeignKey("users.id"), nullable=False)


def upgrade() -> None:
    # Dev startup can build the schema with create_all before Alembic runs. Skipped when Alembic is only rendering SQL.
    if not op.get_context().as_sql and "school_skill_batches" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "school_skill_batches",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("school_id", UUID, sa.ForeignKey("schools.id"), nullable=False),
        sa.Column("module_type", sa.String(20), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("topic", sa.String(120), nullable=True),
        sa.Column("trainer_name", sa.String(120), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        _user("created_by_user_id"),
        *_timestamps(),
        sa.CheckConstraint("module_type IN ('soft_skills', 'digital_skills')", name="ck_skill_batch_module"),
        sa.CheckConstraint("status IN ('open', 'closed')", name="ck_skill_batch_status"),
        sa.CheckConstraint("end_date IS NULL OR end_date >= start_date", name="ck_skill_batch_dates"),
    )
    op.create_index("ix_school_skill_batches_school_module", "school_skill_batches", ["school_id", "module_type"])
    op.create_table(
        "school_skill_enrollments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("batch_id", UUID, sa.ForeignKey("school_skill_batches.id"), nullable=False),
        sa.Column("school_student_id", UUID, sa.ForeignKey("school_students.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("certified_at", sa.DateTime(timezone=True), nullable=True),
        _user("enrolled_by_user_id"),
        *_timestamps(),
        sa.UniqueConstraint("batch_id", "school_student_id", name="uq_skill_enrollment_batch_student"),
        sa.CheckConstraint("status IN ('enrolled', 'completed', 'certified', 'withdrawn')", name="ck_skill_enrollment_status"),
    )
    op.create_index("ix_school_skill_enrollments_school_student_id", "school_skill_enrollments", ["school_student_id"])
    op.create_table(
        "school_skill_sessions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("batch_id", UUID, sa.ForeignKey("school_skill_batches.id"), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("topic", sa.String(160), nullable=True),
        _user("created_by_user_id"),
        *_timestamps(),
        sa.UniqueConstraint("batch_id", "session_date", name="uq_skill_session_batch_date"),
    )
    op.create_table(
        "school_skill_attendance",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("session_id", UUID, sa.ForeignKey("school_skill_sessions.id"), nullable=False),
        sa.Column("enrollment_id", UUID, sa.ForeignKey("school_skill_enrollments.id"), nullable=False),
        sa.Column("present", sa.Boolean(), nullable=False),
        _user("marked_by_user_id"),
        *_timestamps(),
        sa.UniqueConstraint("session_id", "enrollment_id", name="uq_skill_attendance_session_enrollment"),
    )
    op.create_index("ix_school_skill_attendance_enrollment_id", "school_skill_attendance", ["enrollment_id"])
    op.create_table(
        "school_skill_assessments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("batch_id", UUID, sa.ForeignKey("school_skill_batches.id"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("max_score", sa.Numeric(6, 2), nullable=False),
        _user("created_by_user_id"),
        *_timestamps(),
        sa.UniqueConstraint("batch_id", "name", name="uq_skill_assessment_batch_name"),
        sa.CheckConstraint("max_score > 0", name="ck_skill_assessment_max"),
    )
    op.create_table(
        "school_skill_scores",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("assessment_id", UUID, sa.ForeignKey("school_skill_assessments.id"), nullable=False),
        sa.Column("enrollment_id", UUID, sa.ForeignKey("school_skill_enrollments.id"), nullable=False),
        sa.Column("score", sa.Numeric(6, 2), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        _user("recorded_by_user_id"),
        *_timestamps(),
        sa.UniqueConstraint("assessment_id", "enrollment_id", name="uq_skill_score_assessment_enrollment"),
        sa.CheckConstraint("score >= 0", name="ck_skill_score_nonneg"),
    )
    op.create_index("ix_school_skill_scores_enrollment_id", "school_skill_scores", ["enrollment_id"])


def downgrade() -> None:
    # Children before parents; dropping a table drops its indexes and constraints with it.
    for table in ("school_skill_scores", "school_skill_attendance", "school_skill_assessments", "school_skill_sessions", "school_skill_enrollments", "school_skill_batches"):
        op.drop_table(table)
