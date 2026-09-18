"""Add school_academic_results.teacher_remarks (ENH-002).

Revision ID: 0031_academic_result_remarks
Revises: 0030_academic_years

School CRM.md Part B §9's Result Entry field list includes "Teacher Remarks" alongside
Academic Year/Term/Subject/Marks/Grade/Uploaded By -- every other field in that list was
already present on SchoolAcademicResult except this one. Nullable, additive-only: no
backfill, existing rows read as NULL.
"""
import sqlalchemy as sa

from alembic import op

revision = "0031_academic_result_remarks"
down_revision = "0030_academic_years"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {c["name"] for c in inspector.get_columns("school_academic_results")}
    if "teacher_remarks" not in columns:
        op.add_column("school_academic_results", sa.Column("teacher_remarks", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("school_academic_results", "teacher_remarks")
