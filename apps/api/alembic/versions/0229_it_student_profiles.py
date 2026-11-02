"""itc-012 -- the IT student record: it_student_profiles, and enrolment start/end date and delivery-mode overrides.

Revision ID: 0229_it_student_profiles
Revises: 0228_batch_timetable

docs/superpowers/specs/2026-11-02-itc-012-it-student-record-design.md (DEC-SCOPE-345). Additive: a new table and three nullable columns,
no existing row changes (a NULL override means "the batch's"). 0001 builds a fresh database from the current models, which already carry
both, so each is created only when missing (0165's idiom). downgrade() refuses while profiles or overrides exist: a student's personal
details and per-student dates are not dropped silently.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0229_it_student_profiles"
down_revision = "0228_batch_timetable"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
TABLE = "it_student_profiles"
OVERRIDES = (("start_date", sa.Date()), ("end_date", sa.Date()), ("delivery_mode", sa.String(30)))


def upgrade() -> None:
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(op.get_bind())
    if offline or TABLE not in inspector.get_table_names():
        op.create_table(
            TABLE,
            sa.Column("student_user_id", UUID, sa.ForeignKey("users.id"), primary_key=True),
            sa.Column("date_of_birth", sa.Date(), nullable=True),
            sa.Column("address", sa.String(300), nullable=True),
            sa.Column("city", sa.String(80), nullable=True),
            sa.Column("qualification", sa.String(120), nullable=True),
            sa.Column("graduation_year", sa.Integer(), nullable=True),
            sa.Column("emergency_contact_name", sa.String(120), nullable=True),
            sa.Column("emergency_contact_relation", sa.String(60), nullable=True),
            sa.Column("emergency_contact_phone", sa.String(40), nullable=True),
            sa.Column("updated_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    existing = set() if offline else {c["name"] for c in inspector.get_columns("enrollments")}
    for name, type_ in OVERRIDES:
        if name not in existing:
            op.add_column("enrollments", sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    if not op.get_context().as_sql:
        bind = op.get_bind()
        if bind.execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first():
            raise RuntimeError("Cannot downgrade 0229: IT student profiles exist (itc-012)")
        if bind.execute(sa.text("SELECT 1 FROM enrollments WHERE start_date IS NOT NULL OR end_date IS NOT NULL OR delivery_mode IS NOT NULL LIMIT 1")).first():
            raise RuntimeError("Cannot downgrade 0229: enrolment date or mode overrides exist (itc-012)")
    for name, _ in reversed(OVERRIDES):
        op.drop_column("enrollments", name)
    op.drop_table(TABLE)
