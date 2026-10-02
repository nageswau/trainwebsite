"""AGN-013 -- overseas_applications.enrollment_date, university_student_id, enrollment_confirmed_at.

Revision ID: 0058_agent_app_enrollment
Revises: 0057_agent_applications

docs/superpowers/specs/2026-10-02-agn-013-enrollment-confirmation-design.md §3 (DEC-SCOPE-052). Three nullable columns; no
existing row is read or written. 0001 builds a fresh database from the current models, which already carry these columns, so every
add is guarded (0057's idiom). downgrade() refuses while enrollment details exist rather than silently dropping them.
"""

import sqlalchemy as sa

from alembic import op

revision = "0058_agent_app_enrollment"
down_revision = "0057_agent_applications"
branch_labels = None
depends_on = None

TABLE = "overseas_applications"
COLUMNS = (("enrollment_date", sa.Date()), ("university_student_id", sa.String(60)), ("enrollment_confirmed_at", sa.DateTime(timezone=True)))


def upgrade() -> None:
    existing = set() if op.get_context().as_sql else {c["name"] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}
    for name, type_ in COLUMNS:
        if name not in existing:
            op.add_column(TABLE, sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    if not op.get_context().as_sql:
        recorded = " OR ".join(f"{name} IS NOT NULL" for name, _ in COLUMNS)
        if op.get_bind().execute(sa.text(f"SELECT count(*) FROM {TABLE} WHERE {recorded}")).scalar():
            raise RuntimeError("Refusing to downgrade 0058_agent_app_enrollment: enrollment details exist")
    for name, _ in reversed(COLUMNS):
        op.drop_column(TABLE, name)
