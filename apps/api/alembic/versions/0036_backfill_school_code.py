"""Backfill school_code for existing School rows (ENH-009, DEC-SCOPE-023 final review).

Revision ID: 0036_backfill_school_code
Revises: 0035_school_profile_fields

Rows created before 0035 have school_code = NULL, which the ENH-009 admin edit panel's
lookup-by-code flow can never reach, and which fails this feature's own acceptance
criterion ("School ID is generated, unique, and displayed everywhere a school is
currently identified only by name"). Data-only migration: generates a unique 8-char
uppercase hex code (the same convention as core/identifiers.py's generate_student_code())
for every School row where school_code IS NULL. No schema change.

downgrade() is intentionally a no-op: there is no way to distinguish, after the fact,
which NULL-to-code transitions this migration performed versus codes assigned normally
by create_school() to schools created afterward -- a blanket NULL-out would incorrectly
wipe those too. This mirrors this project's existing precedent of not reversing
data-only backfills destructively.
"""
import secrets

import sqlalchemy as sa

from alembic import op

revision = "0036_backfill_school_code"
down_revision = "0035_school_profile_fields"
branch_labels = None
depends_on = None


def _generate_code(existing: set[str]) -> str:
    for _ in range(10):
        code = secrets.token_hex(4).upper()
        if code not in existing:
            return code
    raise RuntimeError("Could not generate a unique school code after 10 attempts")


def upgrade() -> None:
    conn = op.get_bind()
    existing = {row[0] for row in conn.execute(sa.text("SELECT school_code FROM schools WHERE school_code IS NOT NULL"))}
    rows = conn.execute(sa.text("SELECT id FROM schools WHERE school_code IS NULL")).fetchall()
    for (school_id,) in rows:
        code = _generate_code(existing)
        existing.add(code)
        conn.execute(sa.text("UPDATE schools SET school_code = :code WHERE id = :id"), {"code": code, "id": school_id})


def downgrade() -> None:
    pass
