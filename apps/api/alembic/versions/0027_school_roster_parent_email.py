"""Add school_students.pending_parent_email (SCH-001/SCH-003 addendum).

Revision ID: 0027_school_roster_parent_email
Revises: 0026_school_service_delivery

Coordinator now enters a parent's email directly on the roster (single-add, edit, or bulk
upload) instead of only via the separate Team invite page. If that email doesn't already
belong to a school_parent account at this school, the value is held here until the invite
is accepted, at which point every school_student row carrying it gets linked in one pass --
covers a second child added while the first invite is still pending, without a new join
table (`DATA_MODEL.md` §6.11 addendum).
"""
from alembic import op
import sqlalchemy as sa

revision = "0027_school_roster_parent_email"
down_revision = "0026_school_service_delivery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {c["name"] for c in inspector.get_columns("school_students")}
    if "pending_parent_email" not in columns:
        op.add_column("school_students", sa.Column("pending_parent_email", sa.String(255), nullable=True))
        op.create_index("ix_school_students_pending_parent_email", "school_students", ["pending_parent_email"])


def downgrade() -> None:
    op.drop_index("ix_school_students_pending_parent_email", table_name="school_students")
    op.drop_column("school_students", "pending_parent_email")
