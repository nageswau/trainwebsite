"""ccrm-011 -- APP-000001 business IDs on overseas_applications.

Revision ID: 0166_application_codes
Revises: 0165_overseas_student_counselors

docs/superpowers/specs/2026-10-22-ccrm-011-application-codes-design.md (DEC-SCOPE-239). Additive: every existing row keeps its data and
gets an `APP-` code in (created_at, id) order. 0001 builds a fresh database from the current models, which already carry the column, so
each step is guarded (0105's idiom). CODE_DEFAULT repeats app.models.APPLICATION_CODE_DEFAULT (test_ccrm_011_migration). downgrade()
drops the derived code (the UUID stays the key) but keeps the sequence, so a re-upgrade never reissues a code.
"""

import sqlalchemy as sa

from alembic import op

revision = "0166_application_codes"
down_revision = "0165_overseas_student_counselors"
branch_labels = None
depends_on = None

TABLE = "overseas_applications"
SEQ = "overseas_application_code_seq"
CODE_DEFAULT = f"'APP-' || translate(format('%6s', nextval('{SEQ}')), ' ', '0')"
UNIQUE = "uq_overseas_applications_code"


def _inspector():
    return None if op.get_context().as_sql else sa.inspect(op.get_bind())  # offline SQL: emit everything


def upgrade() -> None:
    inspector = _inspector()
    op.execute(sa.text(f"CREATE SEQUENCE IF NOT EXISTS {SEQ}"))
    if inspector is None or "application_code" not in {c["name"] for c in inspector.get_columns(TABLE)}:
        op.add_column(TABLE, sa.Column("application_code", sa.String(20), nullable=True))  # NOT NULL after the backfill
    # One statement: nextval runs over the ordered sub-select, so codes follow (created_at, id).
    op.execute(
        sa.text(
            f"UPDATE {TABLE} a SET application_code = 'APP-' || translate(format('%6s', o.n), ' ', '0') "
            f"FROM (SELECT id, nextval('{SEQ}') AS n FROM (SELECT id FROM {TABLE} WHERE application_code IS NULL ORDER BY created_at, id) s) o "
            "WHERE a.id = o.id"
        )
    )
    op.alter_column(TABLE, "application_code", nullable=False, server_default=sa.text(CODE_DEFAULT))
    if inspector is None or UNIQUE not in {c["name"] for c in inspector.get_unique_constraints(TABLE)}:
        op.create_unique_constraint(UNIQUE, TABLE, ["application_code"])


def downgrade() -> None:
    op.drop_constraint(UNIQUE, TABLE, type_="unique")
    op.drop_column(TABLE, "application_code")
