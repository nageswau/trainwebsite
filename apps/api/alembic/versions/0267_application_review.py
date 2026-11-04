"""hrc-009 -- eligibility-change review: `job_applications.needs_review_since` and its partial index.

Revision ID: 0267_application_review
Revises: 0266_website_intake

docs/superpowers/specs/2026-11-04-hrc-009-eligibility-change-review-design.md (DEC-SCOPE-390 R3). One nullable column, no backfill (no
existing application needs a review). 0001 builds a fresh database from the current models, which already carry them, so each step runs
only when missing (0222's idiom).
"""

import sqlalchemy as sa

from alembic import op

revision = "0267_application_review"
down_revision = "0266_website_intake"
branch_labels = None
depends_on = None

TABLE, COLUMN, INDEX = "job_applications", "needs_review_since", "ix_job_applications_needs_review"


def upgrade() -> None:
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(op.get_bind())
    if offline or COLUMN not in {c["name"] for c in inspector.get_columns(TABLE)}:
        op.add_column(TABLE, sa.Column(COLUMN, sa.DateTime(timezone=True), nullable=True))
    if offline or INDEX not in {i["name"] for i in inspector.get_indexes(TABLE)}:
        op.create_index(INDEX, TABLE, ["job_id"], postgresql_where=sa.text(f"{COLUMN} IS NOT NULL"))


def downgrade() -> None:
    op.drop_index(INDEX, table_name=TABLE, if_exists=True)
    op.drop_column(TABLE, COLUMN)
