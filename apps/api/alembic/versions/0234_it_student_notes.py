"""itc-028 -- internal vs student-visible IT student notes: it_student_notes.

Revision ID: 0234_it_student_notes
Revises: 0232_attendance_leave_policy

docs/superpowers/specs/2026-11-02-itc-028-it-student-notes-design.md (DEC-SCOPE-351). One new table; nothing existing changes (the
overseas `overseas_student_notes` stays). 0001 builds a fresh database from the current models, which already carry it, so the upgrade
is guarded (0222's idiom). The downgrade refuses while a note exists, so it never silently drops a counselling history.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0234_it_student_notes"
down_revision = "0232_attendance_leave_policy"
branch_labels = None
depends_on = None

TABLE = "it_student_notes"


def upgrade() -> None:
    if not op.get_context().as_sql and TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("student_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("author_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("visibility", sa.String(10), nullable=False, server_default="internal"),
        sa.Column("shared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("visibility IN ('internal', 'student')", name="ck_it_student_notes_visibility"),
    )
    op.create_index("ix_it_student_notes_student_created", TABLE, ["student_user_id", "created_at"])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0234: IT student notes exist (itc-028)")
    op.drop_index("ix_it_student_notes_student_created", table_name=TABLE)
    op.drop_table(TABLE)
