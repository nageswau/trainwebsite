"""ccrm-014 -- application sub-status: overseas_applications.sub_status and the history pair.

Revision ID: 0167_application_sub_status
Revises: 0166_application_codes

docs/superpowers/specs/2026-10-22-ccrm-014-application-sub-status-design.md (DEC-SCOPE-240). Additive columns, NULL = not set. 0001
builds a fresh database from the current models, which already carry the columns, so each is added only when missing (0164's idiom).
SS2 backfills only what is certain from existing data; every other row stays NULL. downgrade() drops the columns.
"""

import sqlalchemy as sa

from alembic import op

revision = "0167_application_sub_status"
down_revision = "0166_application_codes"
branch_labels = None
depends_on = None

COLUMNS = (("overseas_applications", "sub_status"), ("application_status_history", "from_sub_status"), ("application_status_history", "to_sub_status"))
BACKFILL = """
UPDATE overseas_applications SET sub_status = CASE
    WHEN status = 'enrolled' THEN 'enrolled'
    WHEN status = 'offer' AND offer_type IN ('conditional', 'unconditional') THEN offer_type || '_offer'
    WHEN status = 'university_selection' AND submitted_on IS NOT NULL THEN 'submitted'
END
WHERE sub_status IS NULL
"""


def _missing(table: str, column: str) -> bool:
    if op.get_context().as_sql:
        return True
    return column not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    for table, column in COLUMNS:
        if _missing(table, column):
            op.add_column(table, sa.Column(column, sa.String(40), nullable=True))
    op.execute(BACKFILL)


def downgrade() -> None:
    for table, column in reversed(COLUMNS):
        op.drop_column(table, column)
