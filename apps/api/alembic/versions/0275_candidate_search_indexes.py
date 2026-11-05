"""hrc-019 -- the advanced candidate search indexes.

Revision ID: 0275_candidate_search_indexes
Revises: 0273_candidate_privacy

docs/superpowers/specs/2026-11-05-hrc-019-advanced-candidate-search-design.md (DEC-SCOPE-399 S12). Indexes only, no data change:
pg_trgm (a trusted extension) with GIN trigram indexes for the case-insensitive *contains* filters on location, institution and
designation, and btree indexes on the normalised current / minimum salary and on the total experience (range filters and sorts). 0001
builds a fresh database from the current models, which already declare the btree ones, so every statement is IF [NOT] EXISTS. The
downgrade drops the indexes and leaves the extension (other objects may come to depend on it).
"""

from alembic import op

revision = "0275_candidate_search_indexes"
down_revision = "0273_candidate_privacy"
branch_labels = None
depends_on = None

BTREE = (
    ("ix_candidates_current_annual_inr", "candidates", "current_annual_inr"),
    ("ix_candidates_minimum_annual_inr", "candidates", "minimum_annual_inr"),
    ("ix_candidates_experience_months", "candidates", "experience_months"),
)
TRIGRAM = (
    ("ix_candidates_location_trgm", "candidates", "location"),
    ("ix_candidate_education_institution_trgm", "candidate_education", "institution"),
    ("ix_candidate_employment_designation_trgm", "candidate_employment", "designation"),
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    for name, table, column in BTREE:
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({column})")
    for name, table, column in TRIGRAM:
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} USING gin ({column} gin_trgm_ops)")


def downgrade() -> None:
    for name, *_ in (*TRIGRAM, *BTREE):
        op.execute(f"DROP INDEX IF EXISTS {name}")
