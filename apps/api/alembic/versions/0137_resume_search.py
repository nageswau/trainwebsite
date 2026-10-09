"""rec-014 -- candidate_resumes.search_vector (generated) + its GIN index.

Revision ID: 0137_resume_search
Revises: 0136_partnership_events

docs/superpowers/specs/2026-10-09-rec-014-resume-full-text-search-design.md §2 (DEC-SCOPE-153, FT8). A STORED generated column, so
Postgres fills it for every existing row on the way in and refreshes it on every extraction; no row's data changes. The table is small
and append-only, so the GIN index is built normally (not CONCURRENTLY). 0001 builds a fresh database from the current models, which
already carry both, so each step runs only when missing (0135's idiom). downgrade() drops them: the vector is derived from the text.

Re-chained on 2026-10-09: drafted as `0136_resume_search` (DEC-SCOPE-152, API §12BT, RBAC §2.78) on `0135_resume_extraction`; upc-011
(`0136_partnership_events`) merged first, so this is `0137` (DEC-SCOPE-153, §12BU, §2.79). A database stamped at the draft is re-stamped
with `alembic stamp --purge 0135_resume_extraction`, then `upgrade head` (both steps here are guarded).
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TSVECTOR

from alembic import op

revision = "0137_resume_search"
down_revision = "0136_partnership_events"
branch_labels = None
depends_on = None

TABLE, COLUMN, INDEX = "candidate_resumes", "search_vector", "ix_candidate_resumes_search"
# Repeats app.models.RESUME_SEARCH_VECTOR (test_rec_014_migration asserts they stay identical).
EXPRESSION = "to_tsvector('english'::regconfig, coalesce(extracted_text, ''))"


def upgrade() -> None:
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(op.get_bind())
    if offline or COLUMN not in {c["name"] for c in inspector.get_columns(TABLE)}:
        op.add_column(TABLE, sa.Column(COLUMN, TSVECTOR(), sa.Computed(EXPRESSION, persisted=True), nullable=True))
    if offline or INDEX not in {i["name"] for i in inspector.get_indexes(TABLE)}:
        op.create_index(INDEX, TABLE, [COLUMN], postgresql_using="gin")


def downgrade() -> None:
    op.drop_index(INDEX, table_name=TABLE)
    op.drop_column(TABLE, COLUMN)
