"""PUB-025 -- IT course card image and syllabus (manual modules, a Drive/https link, or an uploaded PDF).

Revision ID: 0220_program_syllabus_image
Revises: 0219_hr_student_grants

DEC-SCOPE-334. Five nullable/defaulted columns on `programs`; no existing row changes (every course starts with no image and no
syllabus source, so the public page keeps showing its curriculum list). The downgrade drops the columns; uploaded files stay in storage.
"""

import sqlalchemy as sa

from alembic import op

revision = "0220_program_syllabus_image"
down_revision = "0219_hr_student_grants"
branch_labels = None
depends_on = None


COLUMNS = (
    sa.Column("image_url", sa.String(255), nullable=True),
    sa.Column("syllabus_source", sa.String(10), nullable=True),
    sa.Column("syllabus_modules", sa.JSON(), nullable=False, server_default="[]"),
    sa.Column("syllabus_url", sa.String(500), nullable=True),
    sa.Column("syllabus_pdf_url", sa.String(255), nullable=True),
)
CHECK = "ck_programs_syllabus_source"


def upgrade() -> None:
    # 0001 builds a fresh database from the current models, so every step is guarded.
    inspector = None if op.get_context().as_sql else sa.inspect(op.get_bind())
    existing = set() if inspector is None else {c["name"] for c in inspector.get_columns("programs")}
    for column in COLUMNS:
        if column.name not in existing:
            op.add_column("programs", column)
    checks = set() if inspector is None else {c["name"] for c in inspector.get_check_constraints("programs")}
    if CHECK not in checks:
        op.create_check_constraint(CHECK, "programs", "syllabus_source IS NULL OR syllabus_source IN ('manual', 'link', 'pdf')")


def downgrade() -> None:
    op.drop_constraint(CHECK, "programs", type_="check")
    for column in reversed(COLUMNS):
        op.drop_column("programs", column.name)
