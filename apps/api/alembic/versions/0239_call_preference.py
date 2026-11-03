"""itc-033 -- the "phone calls" opt-out on notification preferences.

Revision ID: 0239_call_preference
Revises: 0236_it_at_risk

DEC-SCOPE-357 C1. Two columns on `notification_preferences`: `calls_opt_out` (NOT NULL, default false -- every existing row and every user
without a row reads as "calls allowed", so nothing changes on upgrade) and `calls_opted_out_at` (the consent evidence). 0001 builds a
fresh database from the current models, so each column is added only when missing. Downgrade drops both (no other data is touched).
"""

from alembic import op

revision = "0239_call_preference"
down_revision = "0236_it_at_risk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE notification_preferences ADD COLUMN IF NOT EXISTS calls_opt_out BOOLEAN NOT NULL DEFAULT false")
    op.execute("ALTER TABLE notification_preferences ADD COLUMN IF NOT EXISTS calls_opted_out_at TIMESTAMPTZ")


def downgrade() -> None:
    op.execute("ALTER TABLE notification_preferences DROP COLUMN IF EXISTS calls_opted_out_at")
    op.execute("ALTER TABLE notification_preferences DROP COLUMN IF EXISTS calls_opt_out")
