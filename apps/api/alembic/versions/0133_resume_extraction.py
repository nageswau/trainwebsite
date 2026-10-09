"""rec-012 -- candidate_resumes.extracted_text / extraction_json / extracted_at.

Revision ID: 0133_resume_extraction
Revises: 0132_university_courses

docs/superpowers/specs/2026-10-09-rec-012-resume-extraction-design.md §2 (DEC-SCOPE-148). Three nullable columns; no existing row changes.
0001 builds a fresh database from the current models, which already carry them, so each column is added only when missing (0132's idiom).
downgrade() drops them: their content is derived from the stored resume files and is recomputed by the next extraction.
"""

import sqlalchemy as sa

from alembic import op

revision = "0133_resume_extraction"
down_revision = "0132_university_courses"
branch_labels = None
depends_on = None

TABLE = "candidate_resumes"


def _columns() -> tuple[sa.Column, ...]:
    """Fresh Column objects per call: a Column can be attached to one table only."""
    return (
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("extraction_json", sa.JSON(), nullable=True),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=True),
    )


def upgrade() -> None:
    offline = op.get_context().as_sql
    existing = set() if offline else {c["name"] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}
    for column in _columns():
        if column.name not in existing:
            op.add_column(TABLE, column)


def downgrade() -> None:
    for column in _columns():
        op.drop_column(TABLE, column.name)
