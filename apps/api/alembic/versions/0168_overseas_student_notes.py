"""ccrm-010 -- internal notes on an overseas student: overseas_student_notes.

Revision ID: 0168_overseas_student_notes
Revises: 0167_lead_notes

docs/superpowers/specs/2026-10-22-ccrm-010-student-notes-design.md (DEC-SCOPE-241). Additive: no existing row changes. 0001 builds a fresh
database from the current models, which already carry the table, so it is created only when missing (0165's idiom). downgrade() refuses
while notes exist: a counselling history is not dropped silently.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0168_overseas_student_notes"
down_revision = "0167_lead_notes"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
TABLE = "overseas_student_notes"


def upgrade() -> None:
    if not op.get_context().as_sql and TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        TABLE,
        sa.Column("id", UUID, primary_key=True),
        sa.Column("student_user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("application_id", UUID, sa.ForeignKey("overseas_applications.id"), nullable=True),
        sa.Column("author_user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_overseas_student_notes_student_created", TABLE, ["student_user_id", "created_at"])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0168: student notes exist (ccrm-010)")
    op.drop_index("ix_overseas_student_notes_student_created", table_name=TABLE)
    op.drop_table(TABLE)
