"""itc-009 -- overdue follow-up escalation.

Revision ID: 0226_follow_up_escalation
Revises: 0224_tel_source_workload

DEC-SCOPE-342. `tel_settings` gains `escalate_after_hours` (0-168 whole hours; every existing team starts at 0 = off, so nothing changes
until a manager opts in) and `lead_follow_ups` gains `escalated_at`, the once-only marker. The existing partial index
`ix_lead_follow_ups_open_due` bounds the sweep. 0001 builds a fresh database from the current models, so each column is added only when
missing and the CHECK is dropped and re-created. Both columns are new and only ever hold escalation state, so the downgrade drops them.
"""

from alembic import op

revision = "0226_follow_up_escalation"
down_revision = "0224_tel_source_workload"
branch_labels = None
depends_on = None

MAX_HOURS = 168  # frozen copy of models.TEL_SETTING_MAX_HOURS


def upgrade() -> None:
    op.execute("ALTER TABLE tel_settings ADD COLUMN IF NOT EXISTS escalate_after_hours INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE tel_settings DROP CONSTRAINT IF EXISTS ck_tel_settings_escalate_after_hours")
    op.execute(f"ALTER TABLE tel_settings ADD CONSTRAINT ck_tel_settings_escalate_after_hours CHECK (escalate_after_hours BETWEEN 0 AND {MAX_HOURS})")
    op.execute("ALTER TABLE lead_follow_ups ADD COLUMN IF NOT EXISTS escalated_at TIMESTAMP WITH TIME ZONE")


def downgrade() -> None:
    op.execute("ALTER TABLE lead_follow_ups DROP COLUMN IF EXISTS escalated_at")
    op.execute("ALTER TABLE tel_settings DROP CONSTRAINT IF EXISTS ck_tel_settings_escalate_after_hours")
    op.execute("ALTER TABLE tel_settings DROP COLUMN IF EXISTS escalate_after_hours")
