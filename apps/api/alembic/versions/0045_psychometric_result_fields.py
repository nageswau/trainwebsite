"""ENH-027 -- structured result fields on school_psychometric_records.

Revision ID: 0045_psychometric_result_fields
Revises: 0044_skill_india_certification

docs/superpowers/specs/2026-09-28-enh-027-psychometric-result-fields-design.md §3 (DEC-SCOPE-034). Additive only:
ten nullable columns, no backfill, no constraint, no rewrite of existing rows -- every existing value is kept.
`downgrade()` drops exactly these ten columns.

Re-chained on merge with `main`, 2026-09-28: cut as `0044_psychometric_result_fields` on `0043_portfolio_internship`,
but ENH-024 merged first with `0044_skill_india_certification` on the same parent, so this became `0045` on top of it
(the later-merging branch moves; precedent: 0041's note). Neither touches the other's table.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0045_psychometric_result_fields"
down_revision = "0044_skill_india_certification"
branch_labels = None
depends_on = None

TABLE = "school_psychometric_records"
COLUMNS = (
    ("test_date", sa.Date()),
    ("strengths", postgresql.JSON()),
    ("interest_areas", postgresql.JSON()),
    ("personality_indicators", postgresql.JSON()),
    ("recommended_careers", postgresql.JSON()),
    ("recommended_stream", postgresql.JSON()),
    ("counsellor_remarks", sa.Text()),
    ("parent_discussion_on", sa.Date()),
    ("parent_discussion_notes", sa.Text()),
    ("follow_up_on", sa.Date()),
)


def upgrade() -> None:
    # Guarded: on a fresh database 0001_initial's Base.metadata.create_all() has already built this table from the
    # *current* models, columns included (same reason 0030/0041 guard).
    offline = op.get_context().as_sql
    existing = set() if offline else {c["name"] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}
    for name, type_ in COLUMNS:
        if name not in existing:
            op.add_column(TABLE, sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    for name, _ in reversed(COLUMNS):
        op.drop_column(TABLE, name)
