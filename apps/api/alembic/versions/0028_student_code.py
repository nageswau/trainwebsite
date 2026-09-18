"""Add business-facing Student ID (PRD_OPEN_ITEMS.md item 66 / CLIENT_QUESTIONS.md D-09).

Revision ID: 0028_student_code
Revises: 0027_school_roster_parent_email

8-character uppercase alphanumeric code, resolved 2026-09-15 to apply to every student
population: `users.student_code` for it_student/overseas_student (nullable -- every other
role's value stays NULL) and `school_students.student_code` (never NULL -- every row in
that table is a student). Existing rows are backfilled here since the School table's
column is NOT NULL; app-level generation (`app.core.identifiers.unique_student_code`)
handles every new row going forward.
"""
import secrets

from alembic import op
import sqlalchemy as sa

revision = "0028_student_code"
down_revision = "0027_school_roster_parent_email"
branch_labels = None
depends_on = None


def _generate_unique_codes(conn, table: str, count: int, existing: set[str]) -> list[str]:
    codes: list[str] = []
    while len(codes) < count:
        candidate = secrets.token_hex(4).upper()
        if candidate not in existing:
            existing.add(candidate)
            codes.append(candidate)
    return codes


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    user_columns = {c["name"] for c in inspector.get_columns("users")}
    if "student_code" not in user_columns:
        op.add_column("users", sa.Column("student_code", sa.String(8), nullable=True))
        op.create_index("ix_users_student_code", "users", ["student_code"], unique=True)

        existing = {row[0] for row in bind.execute(sa.text("SELECT student_code FROM users WHERE student_code IS NOT NULL"))}
        rows = bind.execute(sa.text("SELECT id FROM users WHERE role IN ('it_student', 'overseas_student') AND student_code IS NULL")).fetchall()
        if rows:
            codes = _generate_unique_codes(bind, "users", len(rows), existing)
            for (user_id,), code in zip(rows, codes):
                bind.execute(sa.text("UPDATE users SET student_code = :code WHERE id = :id"), {"code": code, "id": user_id})

    school_student_columns = {c["name"] for c in inspector.get_columns("school_students")}
    if "student_code" not in school_student_columns:
        op.add_column("school_students", sa.Column("student_code", sa.String(8), nullable=True))

        existing = {row[0] for row in bind.execute(sa.text("SELECT student_code FROM users WHERE student_code IS NOT NULL"))}
        rows = bind.execute(sa.text("SELECT id FROM school_students WHERE student_code IS NULL")).fetchall()
        if rows:
            codes = _generate_unique_codes(bind, "school_students", len(rows), existing)
            for (student_id,), code in zip(rows, codes):
                bind.execute(sa.text("UPDATE school_students SET student_code = :code WHERE id = :id"), {"code": code, "id": student_id})

        op.alter_column("school_students", "student_code", nullable=False)
        op.create_index("ix_school_students_student_code", "school_students", ["student_code"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_school_students_student_code", table_name="school_students")
    op.drop_column("school_students", "student_code")
    op.drop_index("ix_users_student_code", table_name="users")
    op.drop_column("users", "student_code")
