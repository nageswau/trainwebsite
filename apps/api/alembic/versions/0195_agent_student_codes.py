"""nehn-040 -- a Student ID for agency students with no login, and for student accounts still without one.

Revision ID: 0195_agent_student_codes
Revises: 0194_stored_files

docs/superpowers/specs/2026-10-26-nehn-040-student-id-coverage-design.md (DEC-SCOPE-280 N2-N5). Adds `agent_students.student_code`
(8-char uppercase hex, nullable, unique) only when missing (0001 builds a fresh database from the current models; 0166's idiom), then
backfills every no-login agency row and every it_student/overseas_student account with no code (admin-provisioned accounts had none).
`users` and `agent_students` are one code space, so a new code is never one either table already holds. A linked agency row keeps NULL
and shows its account's code. The downgrade drops the column only; user codes stay.
"""

import secrets

import sqlalchemy as sa

from alembic import op

revision = "0195_agent_student_codes"
down_revision = "0194_stored_files"
branch_labels = None
depends_on = None

INDEX = "ix_agent_students_student_code"


def _fill(bind, table: str, ids: list, taken: set[str]) -> None:
    for row_id in ids:
        code = secrets.token_hex(4).upper()
        while code in taken:
            code = secrets.token_hex(4).upper()
        taken.add(code)
        bind.execute(sa.text(f"UPDATE {table} SET student_code = :code WHERE id = :id"), {"code": code, "id": row_id})


def upgrade() -> None:
    bind = op.get_bind()
    if "student_code" not in {c["name"] for c in sa.inspect(bind).get_columns("agent_students")}:
        op.add_column("agent_students", sa.Column("student_code", sa.String(8), nullable=True))
        op.create_index(INDEX, "agent_students", ["student_code"], unique=True)
    taken = {row[0] for row in bind.execute(sa.text("SELECT student_code FROM users WHERE student_code IS NOT NULL UNION SELECT student_code FROM agent_students WHERE student_code IS NOT NULL"))}
    records = bind.execute(sa.text("SELECT id FROM agent_students WHERE student_id IS NULL AND student_code IS NULL ORDER BY created_at, id")).scalars().all()
    _fill(bind, "agent_students", records, taken)
    accounts = bind.execute(sa.text("SELECT id FROM users WHERE role IN ('it_student', 'overseas_student') AND student_code IS NULL ORDER BY created_at, id")).scalars().all()
    _fill(bind, "users", accounts, taken)


def downgrade() -> None:
    op.drop_index(INDEX, table_name="agent_students")
    op.drop_column("agent_students", "student_code")
