"""Add school_students, school_parent_links, school_activities, school_activity_attendance (SCH-001).

Revision ID: 0024_school_students_activities
Revises: 0023_school_onboarding

`DATA_MODEL.md` §6.11/§6.12. Resolves the §6.11 open schema question (also tracked under
`DEC-ROLE-004`/`PRD_OPEN_ITEMS.md` item 68) as technical contract design: a School-affiliated
student never logs in (`DEC-ROLE-004`), so identity fields live directly on `school_students`,
no `student_user_id` FK -- see `models.py`'s own `SchoolStudent` docstring. `school_activities`/
`school_activity_attendance` are net-new tables covering `SCH-001`'s "schedule activities,
track attendance" workflow line, which had no table proposed anywhere in `DATA_MODEL.md`.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0024_school_students_activities"
down_revision = "0023_school_onboarding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = inspector.get_table_names()

    if "school_students" not in existing:
        op.create_table(
            "school_students",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("school_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("schools.id"), nullable=False),
            sa.Column("full_name", sa.String(160), nullable=False),
            sa.Column("date_of_birth", sa.Date(), nullable=True),
            sa.Column("grade_or_class", sa.String(60), nullable=True),
            sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("assigned_teacher_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_school_students_school_id", "school_students", ["school_id"])

    if "school_parent_links" not in existing:
        op.create_table(
            "school_parent_links",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("parent_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("school_student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("school_students.id"), nullable=False),
            sa.Column("linked_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("parent_user_id", "school_student_id", name="uq_school_parent_link"),
        )
        op.create_index("ix_school_parent_links_parent_user_id", "school_parent_links", ["parent_user_id"])
        op.create_index("ix_school_parent_links_school_student_id", "school_parent_links", ["school_student_id"])

    if "school_activities" not in existing:
        op.create_table(
            "school_activities",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("school_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("schools.id"), nullable=False),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_school_activities_school_id", "school_activities", ["school_id"])

    if "school_activity_attendance" not in existing:
        op.create_table(
            "school_activity_attendance",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("activity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("school_activities.id"), nullable=False),
            sa.Column("school_student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("school_students.id"), nullable=False),
            sa.Column("present", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("marked_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("activity_id", "school_student_id", name="uq_school_activity_attendance"),
        )
        op.create_index("ix_school_activity_attendance_activity_id", "school_activity_attendance", ["activity_id"])
        op.create_index("ix_school_activity_attendance_school_student_id", "school_activity_attendance", ["school_student_id"])


def downgrade() -> None:
    op.drop_table("school_activity_attendance")
    op.drop_table("school_activities")
    op.drop_table("school_parent_links")
    op.drop_table("school_students")
