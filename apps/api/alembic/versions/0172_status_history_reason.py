"""ccrm-016 -- status history with author and reason: application_status_history.outcome and .reason, and the backfill.

Revision ID: 0172_status_history_reason
Revises: 0171_application_offers

docs/superpowers/specs/2026-10-23-ccrm-016-status-history-design.md (DEC-SCOPE-247, H1), after ccrm-023's 0171. Additive and nullable.
0001 builds a fresh database from the current models, which already carry both, so they are added only when missing (0170's idiom).
The backfill touches rows with no outcome only: a history row written in the same transaction as an application_outcomes event (same
application, identical created_at -- both default to the transaction's now()) takes its outcome and reason; a remaining move into
'withdrawn' (AGN-008, before ccrm-015) takes outcome 'withdrawn' and its note as the reason (O1). OUTCOMES repeats
app.application_outcome.OUTCOMES + CLEARED (test_ccrm_016_migration). downgrade() drops both.
"""

import sqlalchemy as sa

from alembic import op

revision = "0172_status_history_reason"
down_revision = "0171_application_offers"
branch_labels = None
depends_on = None

TABLE = "application_status_history"
CHECK = "ck_application_status_history_outcome"
OUTCOMES = ("rejected", "withdrawn", "deferred", "on_hold", "offer_declined", "visa_refused", "cleared")
FROM_EVENTS = f"""
UPDATE {TABLE} h SET outcome = o.outcome, reason = o.reason
FROM application_outcomes o
WHERE o.application_id = h.application_id AND o.created_at = h.created_at AND h.outcome IS NULL
"""
WITHDRAWALS = f"""
UPDATE {TABLE} SET outcome = 'withdrawn', reason = notes
WHERE outcome IS NULL AND to_status = 'withdrawn' AND from_status IS DISTINCT FROM 'withdrawn'
"""


def _inspector():
    return None if op.get_context().as_sql else sa.inspect(op.get_bind())


def upgrade() -> None:
    inspector = _inspector()
    if inspector is None or "outcome" not in {c["name"] for c in inspector.get_columns(TABLE)}:
        op.add_column(TABLE, sa.Column("outcome", sa.String(20), nullable=True))
        op.add_column(TABLE, sa.Column("reason", sa.Text(), nullable=True))
        op.create_check_constraint(CHECK, TABLE, f"outcome IS NULL OR outcome IN ({', '.join(repr(v) for v in OUTCOMES)})")
    op.execute(FROM_EVENTS)
    op.execute(WITHDRAWALS)


def downgrade() -> None:
    op.drop_constraint(CHECK, TABLE, type_="check")
    op.drop_column(TABLE, "reason")
    op.drop_column(TABLE, "outcome")
