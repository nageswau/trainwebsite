"""ENH-005 -- school_student_transfer_requests (a coordinator's transfer request, and the transfer history).

Revision ID: 0034_school_transfer_requests
Revises: 0033_student_grade_history

docs/superpowers/specs/2026-09-21-enh-005-student-school-transfer-design.md §5.1. Create-table only: no existing table is
altered and no existing row is read or written, so there is nothing to backfill. The partial unique index is the
database backstop for "at most one open (pending) request per student". `downgrade()` drops only this table.
Result rows that a later approval sets to the status string `withdrawn` are ordinary data in
`school_academic_results.status` (a plain string column) and are deliberately left alone by a downgrade.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0034_school_transfer_requests"
down_revision = "0033_student_grade_history"
branch_labels = None
depends_on = None

TABLE = "school_student_transfer_requests"


def upgrade() -> None:
    # Dev startup can build the schema with create_all before Alembic runs. Skipped when Alembic is only rendering
    # SQL (`alembic upgrade --sql`), where there is no connection to inspect.
    if not op.get_context().as_sql and TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("school_student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("school_students.id"), nullable=False),
        sa.Column("from_school_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("schools.id"), nullable=False),
        sa.Column("to_school_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("schools.id"), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("filed_by_school_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("schools.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("decided_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("outcome", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("from_school_id <> to_school_id", name="ck_school_transfer_distinct_schools"),
        sa.CheckConstraint("filed_by_school_id IN (from_school_id, to_school_id)", name="ck_school_transfer_filed_by_side"),
    )
    op.create_index(f"ix_{TABLE}_school_student_id", TABLE, ["school_student_id"])
    op.create_index(f"ix_{TABLE}_filed_by_school_id", TABLE, ["filed_by_school_id"])
    op.create_index("uq_school_transfer_pending_student", TABLE, ["school_student_id"], unique=True, postgresql_where=sa.text("status = 'pending'"))


def downgrade() -> None:
    op.drop_index("uq_school_transfer_pending_student", table_name=TABLE)
    op.drop_index(f"ix_{TABLE}_filed_by_school_id", table_name=TABLE)
    op.drop_index(f"ix_{TABLE}_school_student_id", table_name=TABLE)
    op.drop_table(TABLE)
