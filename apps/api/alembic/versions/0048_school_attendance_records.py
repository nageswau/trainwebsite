"""ENH-030 -- school_attendance_records.

Revision ID: 0048_school_attendance_records
Revises: 0047_agent_org_staff

docs/superpowers/specs/2026-09-30-enh-030-daily-attendance-design.md §4. Create-table only: no existing table is altered and no
existing row is read or written. Renumbered from 0046 on merging `main` (AGN-001/002 hold 0046/0047). The unique constraint's index is the only one (spec §11 A4). `downgrade()` drops the table.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0048_school_attendance_records"
down_revision = "0047_agent_org_staff"
branch_labels = None
depends_on = None

TABLE = "school_attendance_records"


def upgrade() -> None:
    if not op.get_context().as_sql and TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("school_student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("school_students.id"), nullable=False),
        sa.Column("school_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("schools.id"), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("marked_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("school_student_id", "school_id", "session_date", name="uq_school_attendance_student_school_date"),
        sa.CheckConstraint("status IN ('present', 'absent', 'late', 'excused')", name="ck_school_attendance_status"),
    )


def downgrade() -> None:
    op.drop_table(TABLE)
