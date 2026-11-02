"""itc-003 -- the IT student -> counselor link: it_student_counselors.

Revision ID: 0222_it_student_counselors
Revises: 0220_program_syllabus_image

docs/superpowers/specs/2026-11-02-itc-003-it-student-counselor-link-design.md (DEC-SCOPE-337). Additive: no existing row changes. 0001
builds a fresh database from the current models, which already carry the table, so it is created only when missing (0165's idiom).
The upgrade backfills one link per IT lead already linked to a student and owned by an IT counselor (the person who linked it is the
assigner); a student already linked is left alone. downgrade() refuses while links exist: a counselor's caseload is not dropped silently.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0222_it_student_counselors"
down_revision = "0220_program_syllabus_image"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
TABLE = "it_student_counselors"
# One lead per student (uq_enquiries_converted_user), so each student appears at most once; NOT EXISTS keeps a re-run harmless.
BACKFILL = f"""
INSERT INTO {TABLE} (id, student_user_id, counselor_user_id, assigned_by_user_id)
SELECT gen_random_uuid(), e.converted_user_id, e.owner_id, e.converted_by_user_id
FROM enquiries e JOIN users c ON c.id = e.owner_id
WHERE e.division = 'it' AND e.converted_user_id IS NOT NULL AND c.role = 'counselor' AND c.division = 'it'
  AND NOT EXISTS (SELECT 1 FROM {TABLE} l WHERE l.student_user_id = e.converted_user_id)
"""


def upgrade() -> None:
    if not op.get_context().as_sql and TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        TABLE,
        sa.Column("id", UUID, primary_key=True),
        sa.Column("student_user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("counselor_user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("assigned_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("student_user_id", name="uq_it_student_counselors_student"),
    )
    op.create_index("ix_it_student_counselors_counselor_user_id", TABLE, ["counselor_user_id"])
    op.execute(BACKFILL)


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0222: IT student-counselor links exist (itc-003)")
    op.drop_index("ix_it_student_counselors_counselor_user_id", table_name=TABLE)
    op.drop_table(TABLE)
